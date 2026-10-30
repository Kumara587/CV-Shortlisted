"""Open-vocabulary, source-grounded JD extraction for the explicit legacy API."""
import re
from matching import prohibited_requirement

KNOWN_SKILLS = ['React', 'JavaScript', 'TypeScript', 'SQL', 'MySQL', 'REST API', 'Git', 'Excel', 'Jira', 'Communication', 'Manual Testing', 'Automation Testing', 'Selenium', 'QA', 'API Testing', 'Python', 'Java', 'Kubernetes', 'Leadership', 'Figma', 'Node.js', 'C++', 'C#', 'AWS', 'Docker', 'FastAPI']
PREFERRED = re.compile(r'added advantage|preferred|preferable|desirable|nice.to.have|optional|bonus|an advantage',re.I)
NOT_REQUIRED = re.compile(r'not (?:strictly )?required|no .{0,30}(?:required|necessary)|not essential',re.I)
HEADINGS = [
 ('education',r'(?:educational? )?qualifications?|education(?:al qualifications?)?|certifications?'),
 ('experience',r'(?:relevant |work |professional )?experience'),
 ('skill',r'(?:required |technical |soft |key )?skills?(?:,? attributes?,? and behavio[u]?r)?|competencies'),
 ('responsibility',r'(?:key |job |main )?(?:responsibilities|duties)|what you.ll do'),
 ('general',r'requirements|what you(?:.ll| will) need'),
 ('other',r'about (?:us|the company)|benefits|how to apply'),
]
DEGREES = [('Diploma',r'\bdiploma\b'),('Bachelor',r"\bbachelor(?:['’]s)?\b|\bb\.?sc\b|\bundergraduate\b"),('Master',r"\bmaster(?:['’]s)?\b|\bm\.?sc\b"),('PhD',r'\bph\.?d\b|\bdoctorate\b')]


def source_clauses(text):
    """Keep every non-heading source clause, including unknown occupations."""
    rows=[]; section=None; pending=None
    def finish():
        nonlocal pending
        if pending:
            rows.append(pending);pending=None
    for line_no,original in enumerate(text.splitlines(),1):
        line=original.strip()
        if not line:
            finish();continue
        clean=re.sub(r'^(?:[•●▪*\-–]\s*|\d+[.)]\s*)','',line).strip()
        heading=None; rest=''
        for category,pattern in HEADINGS:
            match=re.fullmatch(r'('+pattern+r')\s*:?\s*',clean,re.I)
            inline=re.match(r'^('+pattern+r')\s*:\s*(.+)$',clean,re.I)
            if match or inline:
                heading=category;rest=inline.group(2) if inline else '';break
        if heading:
            finish();section=heading
            if not rest: continue
            clean=rest
        bullet=clean!=line or heading is not None
        if pending and not bullet and pending['bullet'] and not re.search(r'[.!?]$',pending['text']):
            pending['text']+=' '+clean
        else:
            finish()
            row_section=section
            if line_no==1 and len(text.splitlines())>1 and not bullet and len(clean.split())<=8 and not re.search(r'[.!?:]|\b(required|experience|skills|degree|must)\b',clean,re.I):
                row_section='other'
            pending={'text':clean,'source_line':line_no,'section':row_section,'bullet':bullet}
    finish()
    clauses=[]
    for row in rows:
        # Avoid splitting school abbreviations such as G.C.E. A/L.
        for sentence in re.split(r'(?<=[a-z0-9])\.\s+(?=[A-Z0-9])|\s*[;•●]\s*',row['text']):
            sentence=sentence.strip(' .')
            if sentence:
                clauses.append({**row,'text':sentence})
    return clauses


def heuristic_category(text,section):
    if re.search(r'\b(?:our company|company has|we have|our team has|established|founded)\b',text,re.I): return 'other'
    if re.search(r'\b(?:G\.?C\.?E\.?|[OA]/L|bachelor|master|degree|diploma|certification|qualification)\b',text,re.I): return 'education'
    if re.search(r'\b(?:years?|months?)\b.*\bexperience\b|\bexperience\b.*\b(?:years?|months?)\b',text,re.I): return 'experience'
    if re.search(r'\b(?:English|Sinhala|Tamil|French|German|Spanish|language)\b.*\b(?:communication|fluency|proficiency)\b|\bcommunication\b.*\b(?:English|Sinhala|Tamil)\b',text,re.I): return 'language'
    if section is None and re.match(r'^(?:support|maintain|coordinate|process|liaise|manage|develop|implement|prepare|perform|conduct|ensure|provide|design|build|deliver)\b',text,re.I): return 'responsibility'
    return None if section=='general' else section or None


def extract_document(text):
    warnings=[]; clauses=source_clauses(text)
    if len(clauses)>100:
        warnings.append('Only the first 100 source clauses were processed. Review the remaining job description.');clauses=clauses[:100]
    categories=[heuristic_category(c['text'],c['section']) for c in clauses]
    warnings.append('Legacy source-based extraction; current AI requests use Gemini.')
    criteria=[]; excluded=False
    for clause,category in zip(clauses,categories):
        value=clause['text']
        if prohibited_requirement(value):
            excluded=True;continue
        category=category or ('skill' if clause['bullet'] else 'other')
        importance='preferred' if PREFERRED.search(value) else 'review' if NOT_REQUIRED.search(value) else 'required' if re.search(r'\b(?:must|required|mandatory|essential|minimum|shall)\b',value,re.I) or category not in {'responsibility','other'} else 'review'
        if len(value)>1000:
            warnings.append('A long clause was shortened for review. Check the original job description.');value=value[:1000]
        criteria.append({'id':f"criterion-{len(criteria)+1}",'text':value,'category':category,'importance':importance,'source_quote':value,'source_line':clause['source_line']})
    skills=[]; seen=set()
    def add(name):
        name=name.strip(' .:')
        if not name or len(name)>60 or name.casefold() in seen or prohibited_requirement(name) or len(skills)>=100: return
        seen.add(name.casefold());skills.append({'name':name,'must':False})
    # Preserve canonical names for familiar tools; unknown skills are not discarded.
    eligible=[c for c in criteria if c['importance']!='preferred' and not NOT_REQUIRED.search(c['text'])]
    for skill in KNOWN_SKILLS:
        if any(re.search(r'(?<!\w)'+re.escape(skill)+r'(?!\w)',c['text'],re.I) for c in eligible): add(skill)
    for criterion in eligible:
        if criterion['category'] in {'skill','language'}:
            for phrase in re.split(r',\s*(?:and\s+)?',criterion['text']):
                phrase=re.sub(r'\s+(?:(?:is|are)\s+)?(?:required|mandatory|essential)$','',phrase,flags=re.I)
                phrase=re.sub(r'^(?:must|should)\s+(?:have|possess|know|demonstrate)\s+','',phrase,flags=re.I)
                phrase=re.sub(r'^(?:excellent|good|strong|proven|ability to|maintaining|knowledge of|proficiency (?:in|with)|experience (?:in|with))\s+','',phrase,flags=re.I)
                if phrase: add(phrase[0].upper()+phrase[1:])
        if criterion['category'] in {'skill','responsibility'}:
            for acronym in re.findall(r'\b[A-Z][A-Z0-9]{2,}\b',criterion['text']):
                if acronym not in {'AND','THE','WITH','FOR','NOT'}: add(acronym)
    years=[]
    for c in eligible:
        if c['category']!='experience': continue
        for match in re.finditer(r'(?<![\w.])(\d{1,3}(?:\.\d{1,2})?)\s*(?:[-–]\s*\d{1,3}(?:\.\d{1,2})?)?\+?\s*(years?|months?)\b',c['text'],re.I):
            n=float(match[1])/(12 if match[2].lower().startswith('month') else 1)
            if n<=60: years.append(n)
    degree=next((name for name,pattern in DEGREES if any(c['category']=='education' and c['importance']=='required' and re.search(pattern,c['text'],re.I) for c in eligible)), '')
    if excluded: warnings.append('Personal/protected-attribute criteria were omitted. Review job-related language proficiency separately from ethnicity.')
    warnings.append('Review every extracted clause and its required/preferred label. Additional criteria are for human review and do not change the current skills/experience/degree score.')
    return {'requirements':{'skills':skills,'minimum_years':min(years) if years else None,'education':degree,'criteria':criteria},
            'method':'source_based_extraction', 'warnings':warnings}
