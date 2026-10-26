import numpy as np
import pytest
from main import Requirements, CandidateInput
from matching import rank_candidates, score_candidate
from semantic import find_matches
from test_security import secured


class RelatedModel:
    def encode(self, texts, **kwargs):
        return np.array([[1., 0.] for _ in texts])


def test_semantic_partial_credit_and_must_have_review():
    result=score_candidate(Requirements(skills=[{'name':'Automated testing','must':True}]),
        CandidateInput(id='a',text='Built regression checks for every release'), RelatedModel())
    assert result['skills'][0]['status']=='semantic_review'
    assert result['score']==50
    assert result['group']=='must_have_review'
    assert result['skills'][0]['evidence'][0]['line_start']==1


@pytest.mark.parametrize('text', ['No Python experience', 'Learning Python', 'Python'])
def test_explicit_evidence_not_overridden(text):
    a=score_candidate(Requirements(skills=[{'name':'Python'}]),CandidateInput(id='a',text=text))
    b=score_candidate(Requirements(skills=[{'name':'Python'}]),CandidateInput(id='a',text=text), RelatedModel())
    assert a['score']==b['score']
    assert a['skills']==b['skills']


def test_demographics_negation_and_uncertainty_excluded():
    rows=[(1,'Gender: Female'),(2,'No experience in regression checks'),
          (3,'Learning regression checks'),(4,'Religion: Buddhist')]
    assert find_matches(['Automated testing'],rows,RelatedModel())=={}


def test_unrelated_vectors_not_matched():
    class Model:
        def encode(self,texts,**kwargs): return np.array([[1.,0.],[0.,1.]])
    assert find_matches(['Python'],[(1,'Prepared financial statements')],Model())=={}


def test_offline_fallback_and_inference_failure(monkeypatch):
    import semantic
    req=Requirements(skills=[{'name':'Python'}])
    candidates=[CandidateInput(id='a',text='Prepared financial statements')]
    monkeypatch.setattr(semantic,'local_model',lambda:None)
    result=rank_candidates(req,candidates,semantic=True)
    assert result['method']=='qualifications-v1'
    assert result['results'][0]['warnings']
    class Broken:
        def encode(self,*args,**kwargs): raise RuntimeError('private input')
    monkeypatch.setattr(semantic,'local_model',lambda:Broken())
    result=rank_candidates(req,candidates,semantic=True)
    assert result['results'][0]['score']==0
    assert 'private input' not in str(result)


def test_window_limit():
    class Model(RelatedModel):
        def encode(self,texts,**kwargs):
            assert len(texts)<=257
            return super().encode(texts,**kwargs)
    assert find_matches(['Testing'],[(i,'Built release checks '*100) for i in range(300)],Model())


def test_semantic_ranking_and_method(monkeypatch):
    import semantic
    monkeypatch.setattr(semantic,'local_model',lambda:RelatedModel())
    req=Requirements(skills=[{'name':'Automated testing'}])
    people=[CandidateInput(id='b',text='Built release regression checks'),
            CandidateInput(id='a',text='Automated testing')]
    result=rank_candidates(req,people,semantic=True)
    assert result['method']=='hybrid-local-semantic-v1'
    assert [r['id'] for r in result['results']]==['a','b']
    assert [r['score'] for r in result['results']]==[100,50]


def test_semantic_api_export_contract(secured,monkeypatch):
    import semantic
    monkeypatch.setattr(semantic,'local_model',lambda:RelatedModel())
    _,client,_,_=secured
    response=client.request('POST','/api/shortlist/match',{
        'reviewed':True,'requirements':{'skills':[{'name':'Automated testing','must':True}]},
        'candidates':[{'id':'a','text':'Built regression checks for each release'}]})
    assert response.status_code==200
    payload=response.json()
    assert payload['method']=='hybrid-local-semantic-v1'
    assert payload['results'][0]['skills'][0]['status']=='semantic_review'
    assert payload['results'][0]['score']==50
    csv=client.request('GET',f"/api/shortlists/{payload['snapshot_id']}/export").text
    assert 'Automated testing' in csv


def test_busy_matching_rejected(secured,monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr('main.match_slots',SimpleNamespace(locked=lambda:True))
    _,client,_,_=secured
    response=client.request('POST','/api/shortlist/match',{
        'reviewed':True,'requirements':{},'candidates':[{'id':'a','text':'Python'}]})
    assert response.status_code==429


def test_real_model_paraphrase():
    from semantic import local_model
    model=local_model()
    if model is None: pytest.skip('Local model not installed')
    result=score_candidate(Requirements(skills=[{'name':'Automated software testing'}]),
        CandidateInput(id='a',text='Created automated tests to verify software functionality and prevent regressions.'), model)
    assert result['skills'][0]['status']=='semantic_review'
    assert result['score']==50
    unrelated=score_candidate(Requirements(skills=[{'name':'Automated software testing'}]),
        CandidateInput(id='b',text='Prepared monthly financial statements and processed invoices.'), model)
    assert unrelated['score']==0
