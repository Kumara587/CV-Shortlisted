"""Deterministic qualification evidence, never an automated hiring decision."""
import re
import unicodedata

VERSION = 'qualifications-v1'
PROTECTED = re.compile(r'\b(age|birth|dob|gender|sex|race|racial|ethnic\w*|nationality|citizenship|religion|religious|disabilit\w*|pregnan\w*|marital|married|single|divorced|sexual|orientation|caste|veteran|political|union|family|parental)\b', re.I)
PERSONAL = re.compile(r'^\s*(?:name|full name|email|phone|mobile|address|location|pronouns|date of birth|dob|age|gender|sex|race|ethnicity|nationality|citizenship|religion|disability|marital status|family status|sexual orientation|veteran status)\s*:', re.I)
NEGATIVE = re.compile(r"\b(?:no|not|never|without|lack\w*|don't|doesn't|haven't)\b", re.I)
UNCERTAIN = re.compile(r'\b(?:learning|studying|pursuing|planned|planning|aspiring|interested|beginner|exposure|familiarity|in progress|expected|candidate for)\b', re.I)
DEGREES = [('Diploma',r'\bdiploma\b'), ('Bachelor',r"\bbachelor(?:['’]s)?\b|\bb\.?sc\.?\b|\bb\.?eng\.?\b"), ('Master',r"\bmaster(?:['’]s)?\b|\bm\.?sc\.?\b|\bm\.?eng\.?\b"), ('PhD',r'\bph\.?d\.?\b|\bdoctorate\b')]
ALIASES = {'node.js':['node.js','nodejs','node js'], 'rest api':['rest api','rest apis','restful api','restful apis']}

def prohibited_requirement(name):
    if re.search(r'\b(?:male|female|young|old)\s+(?:applicants?|candidates?|only)\b|\b(?:applicants?|candidates?)\s+must\s+be\s+(?:male|female)\b',name,re.I): return True
    return bool(PROTECTED.search(unicodedata.normalize('NFKC',name))) or name.casefold() in {'male','female','christian','buddhist','muslim','hindu','sinhala','tamil','white','black','asian','young','old','woman','man','women','men','sri lankan','indian','sinhalese','heterosexual','homosexual'}

def segments(text):
    """References use original parsed-text lines, never reconstructed page numbers."""
    for number, line in enumerate(text.splitlines(),1):
        if PERSONAL.match(line):
            continue
        for match in re.finditer(r'[^;\n]+',line):
            snippet = match.group().strip()
            # Ignore explicitly labeled demographics, including inline semicolon fields.
            if PERSONAL.match(snippet):
                continue
            yield number, snippet

def evidence(source_id,line,quote,focus=0):
    start=max(0,focus-120)
    excerpt=quote[start:start+500]
    return {'source_id':source_id,'line_start':line,'line_end':line,'quote':excerpt, 'truncated':start+500<len(quote), 'truncated_before':start>0}

def skill_pattern(name):
    aliases=ALIASES.get(name.casefold(),[name])
    parts=[r'\s+'.join(re.escape(token) for token in unicodedata.normalize('NFKC',a).split()) for a in aliases]
    return re.compile(r'(?<![\w+#])(?:'+ '|'.join(parts)+r')(?![\w+#])',re.I)

def score_candidate(requirements, candidate):
    source=candidate.id
    rows=list(segments(candidate.text))
    criteria=[]
    for skill in requirements.skills:
        pattern=skill_pattern(skill.name)
        found=[]
        states=set()
        for line,quote in rows:
            normalized=unicodedata.normalize('NFKC',quote)
            if pattern.search(normalized):
                # Sentence/clause context avoids a negation in an unrelated sentence.
                for clause in re.split(r'(?<=[.!?])\s+|\bbut\b',quote):
                    if pattern.search(unicodedata.normalize('NFKC',clause)):
                        state='contradicted' if NEGATIVE.search(clause) else 'uncertain' if UNCERTAIN.search(clause) else 'supported'
                        states.add(state)
                        if len(found)<3: found.append((state,evidence(source,line,clause.strip(),(pattern.search(clause.strip()) or pattern.search(unicodedata.normalize('NFKC',clause.strip()))).start())))
        state=('uncertain' if len(states)>1 else next(iter(states))) if states else 'not_evidenced'
        criteria.append({'name':skill.name,'must':skill.must,'status':state,'credit':1 if state=='supported' else 0,'reason':{'supported':'Explicit skill mention; self-reported, proficiency unverified.','uncertain':'Learning/limited context or conflicting claims; verify with the candidate.','contradicted':'A negated skill claim was found; verify context.','not_evidenced':'No explicit supported mention found; this does not prove the skill is absent.'}[state], 'evidence':[item for _,item in found[:3]]})
    experience={'status':'not_required','years':None,'reason':'No positive minimum experience requirement.','evidence':[],'credit':None}
    minimum=requirements.minimum_years
    if minimum is not None and minimum>0:
        claims=[]
        pattern=re.compile(r'(?<![\w.])(?P<low>\d{1,3}(?:\.\d{1,2})?)\s*(?:[-–]\s*(?P<high>\d{1,3}(?:\.\d{1,2})?))?\+?\s*years?\s+(?:of\s+)?(?:(?:total|relevant|practical|professional|work|software|development|industry)\s+){0,3}experience\b',re.I)
        for line,quote in rows:
            for match in pattern.finditer(quote):
                low=float(match['low'])
                high=float(match['high']) if match['high'] else low
                state='uncertain' if NEGATIVE.search(quote) or UNCERTAIN.search(quote) or low>60 or high<low or high>60 else 'supported'
                claims.append((low,high,state,evidence(source,line,quote,match.start())))
        values={(low,high) for low,high,state,_ in claims if state=='supported'}
        if claims and (len(values)!=1 or any(state!='supported' for _,_,state,_ in claims)):
            experience.update(status='uncertain',reason='Conflicting, implausible or qualified experience claims; no duration is inferred from employment or birth dates.',credit=0)
        elif values:
            low,high=next(iter(values))
            state='meets' if low>=minimum else 'uncertain' if high>=minimum else 'below_requirement'
            experience.update(status=state,years=low,credit=1 if state=='meets' else 0,reason=f'Self-reported experience {low:g}–{high:g} years; requires {minimum:g}. Range uses its lower bound. Relevance and dates require review.')
        else:
            experience.update(status='not_evidenced',credit=0,reason='No explicit years-of-experience claim found. Missing information is not zero experience; dates and age are not used.')
        experience['evidence']=[ev for *_,ev in claims[:3]]
    education={'status':'not_required','level':None,'reason':'No education requirement.','evidence':[],'credit':None}
    if requirements.education:
        completed=[]; pending=[]
        for line,quote in rows:
            for rank,(name,pattern) in enumerate(DEGREES):
                if re.search(pattern,quote,re.I):
                    item=(rank,name,evidence(source,line,quote,re.search(pattern,quote,re.I).start()))
                    (pending if NEGATIVE.search(quote) or UNCERTAIN.search(quote) else completed).append(item)
        required=[name for name,_ in DEGREES].index(requirements.education)
        if completed:
            rank,name,ev=max(completed,key=lambda x:x[0])
            conflict=any(r==rank and NEGATIVE.search(ev['quote']) for r,_,ev in pending)
            state='uncertain' if conflict else 'meets' if rank>=required else 'uncertain' if any(r>=required for r,_,_ in pending) else 'below_requirement'
            education.update(status=state,level=name,credit=1 if state=='meets' else 0,reason=('Conflicting completed and negated education claims; verify qualification.' if conflict else f'Self-reported {name}; requires {requirements.education}. Institution, prestige and graduation year are not scored.'),evidence=[ev]+[ev for _,_,ev in pending[:2]])
        else:
            education.update(status='uncertain' if pending else 'not_evidenced',credit=0,reason='Only incomplete/negated education claims found; verify completion.' if pending else 'No recognized degree claim found; verify qualification or equivalent experience.',evidence=[ev for _,_,ev in pending[:3]])
    weights={'skills':80 if criteria else 0,'experience':10 if minimum is not None and minimum>0 else 0,'education':10 if requirements.education else 0}
    components={}
    total=sum(weights.values())
    for name,fraction in [('skills',sum(s['credit'] for s in criteria)/len(criteria) if criteria else None),('experience',experience['credit']),('education',education['credit'])]:
        weight=weights[name]
        components[name]={'weight':round(weight/total*100,4) if total else 0,'credit':fraction,'points':round(weight/total*100*(fraction or 0),4) if total else 0}
    usable=candidate.parse_status=='parsed' and bool(candidate.text.strip())
    must_issues=[{'name':s['name'],'status':s['status']} for s in criteria if s['must'] and s['status']!='supported']
    score=round(sum(c['points'] for c in components.values()),2) if usable and total else None
    group='unscored' if score is None else 'must_have_review' if must_issues else 'requirements_review'
    uncertainties=[s['name'] for s in criteria if s['status']!='supported']
    if experience['status'] not in {'meets','not_required'}: uncertainties.append('experience')
    if education['status'] not in {'meets','not_required'}: uncertainties.append('education')
    return {'additional_criteria':[c.model_dump() for c in requirements.criteria],'id':source,'score':score,'group':group,'skills':criteria,'experience':experience,'education':education,'components':components,'must_have_issues':must_issues,'missing_or_uncertain':uncertainties,'review_status':'pending','review_required':True,'warnings':(['No usable parsed text; no score assigned.'] if not usable else [])+(['No active requirements; no score assigned.'] if not total else [])+list(candidate.warnings),'method':VERSION}

def rank_candidates(requirements,candidates):
    results=[score_candidate(requirements,c) for c in candidates]
    method=VERSION
    # Ties use opaque source IDs, not names, protected attributes or text order.
    priority={'requirements_review':0,'must_have_review':1,'unscored':2}
    results.sort(key=lambda r:(priority[r['group']],-(r['score'] if r['score'] is not None else -1),r['id']))
    for rank,result in enumerate(results,1): result['rank']=rank
    return {'method':method,'requirements':requirements.model_dump(),'results':results,'notice':'Explicit legacy matching only. ''Evidence coverage only, not predicted job performance or a hiring decision. Every candidate requires human review. Missing evidence does not prove missing ability. Rankings separate must-have review cases; no candidate is automatically rejected.'}
