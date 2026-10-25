import json
import pytest
from pydantic import ValidationError
from main import Requirements, CandidateInput, MatchRequest, match_shortlist
from matching import rank_candidates


def match(text, skills=None, years=None, education='', **kwargs):
    req=Requirements(skills=skills or [], minimum_years=years, education=education)
    c=CandidateInput(id='candidate-a',text=text,**kwargs)
    return rank_candidates(req,[c])['results'][0]

def test_weighted_score_and_references():
    text='Name: Ada\nSkills: Python, SQL\n3 years of experience\nBachelor degree'
    result=match(text,[{'name':'Python'},{'name':'SQL'}],2,'Bachelor')
    assert result['score']==100 and result['review_required']
    assert result['components']['skills']['points']==80
    ev=result['skills'][0]['evidence'][0]
    assert ev['source_id']=='candidate-a' and ev['line_start']==2
    assert ev['quote'] in text.splitlines()[ev['line_start']-1]

@pytest.mark.parametrize('text,skill,status', [
    ('JavaScript MySQL','Java','not_evidenced'), ('JavaScript MySQL','SQL','not_evidenced'),
    ('C++ C#','C++','supported'), ('NodeJS','Node.js','supported'),
    ('No Python experience','Python','contradicted'), ('Learning Python','Python','uncertain'),
    ('Python\nNo Python experience','Python','uncertain'), ('No SQL. Python projects','Python','supported'),
])
def test_skill_uncertainty(text,skill,status):
    r=match(text,[{'name':skill,'must':True}])
    assert r['skills'][0]['status']==status
    assert bool(r['must_have_issues'])==(status!='supported')
    assert r['score']==(100 if status=='supported' else 0)

def test_missing_is_unknown_and_active_weights():
    r=match('Python',[{'name':'Python'}],3,'Bachelor')
    assert r['score']==80 and r['experience']['years'] is None
    assert r['experience']['status']=='not_evidenced'
    assert r['education']['status']=='not_evidenced'
    assert match('Python',[{'name':'Python'}])['score']==100
    assert match('Unrelated text')['score'] is None
    assert match('',[{'name':'Python'}],parse_status='needs_text')['score'] is None

@pytest.mark.parametrize('text,minimum,status,years', [
    ('2.5 years of experience',2,'meets',2.5), ('2-4 years of experience',3,'uncertain',2),
    ('1 year of experience',3,'below_requirement',1), ('3 years of experience\n5 years of experience',2,'uncertain',None),
    ('Born 1980. Worked 2000-2025',2,'not_evidenced',None), ('31 years old',2,'not_evidenced',None),
    ('No 3 years of experience',2,'uncertain',None),
])
def test_experience(text,minimum,status,years):
    r=match(text,years=minimum)
    assert r['experience']['status']==status and r['experience']['years']==years

@pytest.mark.parametrize('text,required,status', [
    ('Master degree','Bachelor','meets'), ('Diploma','Bachelor','below_requirement'),
    ('Pursuing Bachelor degree','Bachelor','uncertain'), ('Bachelor degree expected 2027','Bachelor','uncertain'),
    ('No Bachelor degree','Bachelor','uncertain'), ('Bachelor degree from Example University 1990','Bachelor','meets'),
])
def test_education(text,required,status):
    assert match(text,education=required)['education']['status']==status

def test_protected_attributes_do_not_change_scores():
    base='Skills: Python\n3 years of experience\nBachelor degree'
    profile='Name: Python Smith\nGender: Female\nAge: 54\nReligion: Buddhist\nNationality: Sri Lankan\nDisability: Yes\nMarital status: Married\n'
    a=match(base,[{'name':'Python'}],2,'Bachelor')
    b=match(profile+base,[{'name':'Python'}],2,'Bachelor')
    assert a['score']==b['score']==100
    assert a['components']==b['components']
    assert match('Name: Python Smith\nEmail: python@example.com',[{'name':'Python'}])['score']==0
    assert all('Female' not in ev['quote'] for c in b['skills'] for ev in c['evidence'])

@pytest.mark.parametrize('skill',['Age','Gender','Religion','Nationality','Marital status','Disability','Female'])
def test_protected_requirements_rejected(skill):
    with pytest.raises(ValidationError): Requirements(skills=[{'name':skill}])

def test_stable_ranking_and_must_have_separation():
    req=Requirements(skills=[{'name':'Python','must':True},{'name':'SQL'}])
    candidates=[CandidateInput(id='z',text='Python'),CandidateInput(id='a',text='Python'),CandidateInput(id='b',text='SQL'),CandidateInput(id='c',text='',parse_status='error')]
    a=rank_candidates(req,candidates)['results']
    b=rank_candidates(req,list(reversed(candidates)))['results']
    assert [r['id'] for r in a]==[r['id'] for r in b]==['a','z','b','c']
    assert a[2]['group']=='must_have_review' and a[3]['group']=='unscored'
    assert a[2]['review_status']=='pending' # never auto-rejected

def test_review_and_unique_id_validation():
    with pytest.raises(ValidationError): MatchRequest(requirements={},reviewed=False,candidates=[{'id':'a','text':'Python'}])
    with pytest.raises(ValidationError): MatchRequest(requirements={},reviewed=True,candidates=[{'id':'a','text':'Python'}]*2)

def test_route_without_network():
    body=MatchRequest(requirements={'skills':[{'name':'Python'}]},reviewed=True,candidates=[{'id':'a','text':'Python'}])
    from types import SimpleNamespace
    class SnapshotStore:
        def save(self,*args): return 'snapshot-test',123456
    request=SimpleNamespace(state=SimpleNamespace(user_id='owner'),app=SimpleNamespace(state=SimpleNamespace(store=SnapshotStore())))
    coroutine=match_shortlist(body,request)
    with pytest.raises(StopIteration) as done: coroutine.send(None)
    response=done.value.value
    assert response.headers['cache-control']=='no-store'
    assert json.loads(response.body)['results'][0]['score']==100


def test_contradictory_education_is_uncertain():
    assert match('Bachelor degree completed\nNo Bachelor degree',education='Bachelor')['education']['status']=='uncertain'

def test_gate_is_separate_from_score():
    req=Requirements(skills=[{'name':'Python','must':True},{'name':'SQL'}],minimum_years=1,education='Bachelor')
    people=[CandidateInput(id='a',text='Python'), CandidateInput(id='b',text='SQL\n3 years of experience\nBachelor degree')]
    results=rank_candidates(req,people)['results']
    assert results[0]['score']==40 and results[1]['score']==60
    assert results[0]['group']=='requirements_review' and results[1]['group']=='must_have_review'
    assert results[1]['must_have_issues'][0]['name']=='Python'

def test_model_bounds_and_protected_metadata():
    with pytest.raises(ValidationError): CandidateInput(id='a',text='Python',gender='female')
    with pytest.raises(ValidationError): CandidateInput(id='a',text='x'*200001)
    with pytest.raises(ValidationError): MatchRequest(requirements={},reviewed=True,candidates=[])


def test_line_references_include_nonstandard_separators():
    r=match('Name: Ada\rPython\fSQL',[{'name':'SQL'}])
    assert r['skills'][0]['evidence'][0]['line_start']==3


def test_long_evidence_excerpt_keeps_matching_term():
    result=match('Long project description '+('detail '*100)+'Python',[{'name':'Python'}])
    evidence=result['skills'][0]['evidence'][0]
    assert 'Python' in evidence['quote'] and len(evidence['quote'])<=500
