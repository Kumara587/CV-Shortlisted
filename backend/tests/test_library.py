import sqlite3
import pytest
from test_security import secured
from store import Store


def workspace(title='QA Engineer'):
    return {'title':title,'job_description':'Python developer with testing skills.',
            'requirements':{'skills':[{'name':'Python','must':True}]},
            'candidates':[{'id':'a','display_label':'Resume.txt','text':'Python\n3 years of experience'}]}


def create(client):
    response=client.request('POST','/api/jobs',workspace())
    assert response.status_code==201,response.text
    return response.json()['id']


def screen(client,job_id):
    w=workspace()
    response=client.request('POST','/api/shortlist/match',{
        'job_id':job_id,'reviewed':True,'requirements':w['requirements'],'candidates':w['candidates']})
    assert response.status_code==200,response.text
    return response.json()['snapshot_id']


def test_job_cv_persistence_after_reconnect(secured):
    store,a,_,_=secured
    job_id=create(a)
    reopened=Store(store.path)
    owner=a.app.state.store.authenticate(a.token)
    job=reopened.job(owner,job_id)
    assert job['workspace']['candidates'][0]['text'].startswith('Python')
    assert reopened.list_jobs(owner)[0]['title']=='QA Engineer'
    updated=workspace('Senior QA Engineer')
    assert a.request('PATCH','/api/jobs/'+job_id,updated).status_code==200
    assert a.request('GET','/api/jobs/'+job_id).json()['workspace']['title']=='Senior QA Engineer'


def test_runs_history_reviews_csv_and_retention(secured):
    store,a,_,_=secured
    job_id=create(a); run_id=screen(a,job_id)
    assert run_id.startswith('run_')
    original=a.request('GET','/api/screenings/'+run_id).json()
    assert original['result']['results'][0]['score']==100
    assert original['workspace']['candidates'][0]['text'].startswith('Python')
    assert a.request('PATCH',f'/api/shortlists/{run_id}/reviews',{'candidate_id':'a','status':'shortlisted'}).status_code==200
    assert a.request('GET','/api/screenings/'+run_id).json()['result']['results'][0]['review_status']=='shortlisted'
    assert 'shortlisted' in a.request('GET',f'/api/shortlists/{run_id}/export').text
    store.clock=lambda:10**12
    store.purge()
    assert a.request('DELETE','/api/shortlists').status_code==200
    assert a.request('GET','/api/screenings/'+run_id).status_code==200
    assert a.request('GET',f'/api/shortlists/{run_id}/export').status_code==200
    assert len(a.request('GET',f'/api/jobs/{job_id}/runs').json()['runs'])==1


def test_owner_and_anonymous_access(secured):
    _,a,b,anon=secured
    job_id=create(a); run_id=screen(a,job_id)
    assert b.request('GET','/api/jobs').json()=={'jobs':[]}
    for method,path,body in [
        ('GET',f'/api/jobs/{job_id}',None),('PATCH',f'/api/jobs/{job_id}',workspace()),
        ('DELETE',f'/api/jobs/{job_id}',None),('GET',f'/api/jobs/{job_id}/runs',None),
        ('GET',f'/api/screenings/{run_id}',None),('DELETE',f'/api/screenings/{run_id}',None),
        ('GET',f'/api/shortlists/{run_id}/export',None),
        ('PATCH',f'/api/shortlists/{run_id}/reviews',{'candidate_id':'a','status':'reviewed'})]:
        assert b.request(method,path,body).status_code==404
        assert anon.request(method,path,body).status_code==401
    w=workspace()
    assert b.request('POST','/api/shortlist/match',{'job_id':job_id,'reviewed':True,
        'requirements':w['requirements'],'candidates':w['candidates']}).status_code==404


def test_historical_inputs_immutable_and_cascade_delete(secured):
    store,a,_,_=secured
    job_id=create(a); run_id=screen(a,job_id)
    changed=workspace('Another job');changed['candidates']=[]
    assert a.request('PATCH','/api/jobs/'+job_id,changed).status_code==200
    assert a.request('GET','/api/screenings/'+run_id).json()['workspace']['title']=='QA Engineer'
    assert a.request('DELETE','/api/jobs/'+job_id).status_code==204
    assert a.request('GET','/api/screenings/'+run_id).status_code==404
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT count(*) FROM screenings').fetchone()[0]==0


def test_delete_individual_run_keeps_job(secured):
    _,a,_,_=secured
    job_id=create(a); run_id=screen(a,job_id)
    assert a.request('DELETE','/api/screenings/'+run_id).status_code==204
    assert a.request('GET','/api/jobs/'+job_id).status_code==200
    assert a.request('GET',f'/api/jobs/{job_id}/runs').json()=={'runs':[]}
    assert a.request('GET',f'/api/shortlists/{run_id}/export').status_code==404


@pytest.mark.parametrize('change',[{'title':' '},{'title':'x'*161},{'job_description':'x'*20001},
                                  {'requirements':{'skills':[{'name':'Gender'}]}},
                                  {'candidates':[workspace()['candidates'][0]]*2}])
def test_validation(secured,change):
    _,a,_,_=secured
    w=workspace(); w.update(change)
    assert a.request('POST','/api/jobs',w).status_code==422


def test_migration_preserves_existing_users(secured):
    store,a,_,_=secured
    assert Store(store.path).authenticate(a.token)
    assert Store(store.path).authenticate(a.token)==store.authenticate(a.token)


def test_storage_quota_and_failed_update_keeps_original(secured,monkeypatch):
    _,a,_,_=secured
    job_id=create(a)
    monkeypatch.setattr('library.MAX_LIBRARY_BYTES',1)
    assert a.request('POST','/api/jobs',workspace()).status_code==409
    assert a.request('PATCH','/api/jobs/'+job_id,workspace('Changed')).status_code==409
    assert a.request('GET','/api/jobs/'+job_id).json()['workspace']['title']=='QA Engineer'
    w=workspace()
    assert a.request('POST','/api/shortlist/match',{'job_id':job_id,'reviewed':True,
        'requirements':w['requirements'],'candidates':w['candidates']}).status_code==409
    assert a.request('GET',f'/api/jobs/{job_id}/runs').json()=={'runs':[]}
