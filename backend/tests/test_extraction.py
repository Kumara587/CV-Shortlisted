import re
import pytest
from extraction import extract_document
from main import Requirements, CandidateInput
from matching import rank_candidates

HR_JOB='''HR Assistant
• Support the end-to-end recruitment process for interns, chartered trainees, actuarial trainees, and outsourced staff, including interview coordination and onboarding.
• Maintain accurate employee records by managing HRIS updates, personal files, attendance, and HR documentation.
• Coordinate administrative processes such as issuing service letters, access credentials, dummy numbers, and handling employee requests related to interns and outsourced staff.
• Process payments, prepare reports, and maintain databases related to interns and outsourced staff, ensuring accuracy and timely completion.
• Liaise with internal departments to provide HR and administrative support while ensuring compliance with company policies and procedures.

Qualification
• Passed G.C.E A/L with three main subjects AND
• Passed G.C.E. O/L with credit passes for mathematics, English, and Sinhala/Tamil (within two sittings)
• Possession of a degree or a part professional qualification in Human Resource Management (HRM) will be considered an added advantage.

Relevant Experience
• Minimum of 1 year of experience in the HR field.

Skills, Attributes, and Behavior
• Maintaining confidentiality
• Excellent communication skills in Sinhala/Tamil and English
• Good interpersonal skills
• Teamwork
• Ability to work under pressure
• Timeliness, quality, and accuracy of work'''


def test_hr_job_preserves_qualifications_soft_skills_and_preferences():
    data=extract_document(HR_JOB)
    req=Requirements(**data['requirements'])
    assert req.minimum_years==1
    assert req.education=='' # an added advantage is not a mandatory degree
    names={s.name.casefold() for s in req.skills}
    assert {'confidentiality','interpersonal skills','teamwork','work under pressure','timeliness','quality','accuracy of work','hris'}<=names
    assert any('Sinhala/Tamil and English' in s.name for s in req.skills)
    assert any('A/L' in c.text and c.importance=='required' for c in req.criteria)
    assert any('O/L' in c.text and 'two sittings' in c.text and c.importance=='required' for c in req.criteria)
    assert any('HRM' in c.text and c.importance=='preferred' for c in req.criteria)
    normalized=re.sub(r'\s+',' ',HR_JOB)
    assert all(c.source_quote in normalized for c in req.criteria)


@pytest.mark.parametrize('job,expected',[
    ('Chef\nSkills:\n• Knife handling\n• HACCP\n• Menu planning',{'Knife handling','HACCP','Menu planning'}),
    ('Nurse\nSkills:\n• Wound dressing\n• Patient care\nQualifications:\n• Valid nursing registration',{'Wound dressing','Patient care'}),
    ('Accountant\nSkills:\n• Bank reconciliation\n• IFRS\n• Tax preparation',{'Bank reconciliation','IFRS','Tax preparation'}),
    ('Technician\nSkills: Optical alignment, vacuum maintenance, photolithography',{'Optical alignment','Vacuum maintenance','Photolithography'}),
])
def test_unknown_occupation_skills_not_limited_to_catalog(job,expected):
    req=extract_document(job)['requirements']
    assert expected<={s['name'] for s in req['skills']}


def test_preferred_and_negated_do_not_become_mandatory():
    req=extract_document('Requirements:\n• Python not required. SQL required.\n• Bachelor degree preferred.\nExperience:\n• 2 years of experience preferred.')['requirements']
    assert [s['name'] for s in req['skills']]==['SQL']
    assert req['education']=='' and req['minimum_years'] is None
    assert any(c['importance']=='preferred' for c in req['criteria'])


def test_months_and_field_context_and_company_age():
    req=extract_document('Experience:\nMinimum 12 months of experience in HR.\nOur company has 20 years of experience.')['requirements']
    assert req['minimum_years']==1


def test_general_required_clause_and_wrapped_language_text():
    data=extract_document('Requirements:\n• Must possess specialist equipment expertise\nSkills:\n• Excellent communication skills in\nSinhala/Tamil and English')
    criteria=data['requirements']['criteria']
    assert criteria[0]['importance']=='required'
    assert any(c['text']=='Excellent communication skills in Sinhala/Tamil and English' and c['category']=='language' for c in criteria)


def test_unsupported_and_long_criteria_are_visible_not_silently_discarded():
    sentence='Ability to perform '+('specialized unfamiliar operations '*40)
    data=extract_document('Skills:\n• '+sentence)
    assert data['requirements']['criteria']
    assert len(data['requirements']['criteria'][0]['text'])==1000
    assert any('shortened' in w for w in data['warnings'])


def test_protected_attributes_excluded_but_languages_preserved():
    data=extract_document('Requirements:\n• Female applicants only\nSkills:\n• Communication skills in Sinhala/Tamil and English')
    assert all('Female' not in c['text'] for c in data['requirements']['criteria'])
    assert any(c['category']=='language' for c in data['requirements']['criteria'])


def test_additional_criteria_survive_matching_without_inflating_score():
    req=Requirements(**extract_document(HR_JOB)['requirements'])
    result=rank_candidates(req,[CandidateInput(id='a',text='Teamwork')])['results'][0]
    assert result['additional_criteria']==[c.model_dump() for c in req.criteria]
    assert all('credit' not in c for c in result['additional_criteria'])


def test_local_ai_extraction_retains_grounded_clauses():
    from semantic import local_model
    if local_model() is None: pytest.skip('Local model is unavailable')
    data=extract_document(HR_JOB,True)
    assert data['method']=='local_semantic_extraction'
    assert data['requirements']['minimum_years']==1
    assert any('O/L' in c['text'] for c in data['requirements']['criteria'])
