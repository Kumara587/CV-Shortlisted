import pytest
from test_security import secured

@pytest.fixture
def client(secured):
    actual=secured[1]
    class Adapter:
        def get(self,path,**kw): return actual.request('GET',path,headers=kw.get('headers'))
        def post(self,path,**kw): return actual.request('POST',path,body=kw.get('json'),headers=kw.get('headers'))
        def options(self,path,**kw): return actual.request('OPTIONS',path,headers=kw.get('headers'))
    return Adapter()

def test_health(client):
    assert client.get('/health').json()['status'] == 'ok'

def test_extraction_boundaries_and_experience(client):
    r = client.post('/api/requirements/extract', json={'job_description': 'JavaScript, Python, C++ and Git. Bachelor degree. 3-5 years of relevant experience.'})
    assert r.status_code == 200
    body = r.json()
    assert body['method'] in {'local_semantic_extraction','source_based_extraction'}
    assert [s['name'] for s in body['requirements']['skills']] == ['JavaScript', 'Git', 'Python', 'C++']
    assert body['requirements']['minimum_years'] == 3
    assert body['requirements']['education'] == 'Bachelor'

def test_unknown_is_not_zero(client):
    r = client.post('/api/requirements/extract', json={'job_description': 'Our company has operated for 20 years. Join our team.'})
    req=r.json()['requirements']
    assert req['skills']==[] and req['minimum_years'] is None and req['education']==''
    assert req['criteria'][0]['importance']=='review'

@pytest.mark.parametrize('body', [{}, {'job_description': ' '}, {'job_description': 'x'*20001}, {'job_description': 123}, {'job_description': 'valid description for a job', 'extra': True}])
def test_invalid_extraction(body, client):
    r = client.post('/api/requirements/extract', json=body)
    assert r.status_code == 422
    assert all('input' not in e for e in r.json()['detail'])

def test_manual_contract(client):
    body = {'skills': [{'name': 'Custom skill', 'must': True}], 'minimum_years': 2.5, 'education': 'Diploma'}
    assert client.post('/api/requirements/validate', json=body).json() == {**body,'criteria':[]}

@pytest.mark.parametrize('body', [{'minimum_years': -1}, {'minimum_years': 61}, {'education': 'invalid'}, {'skills': [{'name': ' '}]}, {'skills': [{'name': 'SQL'}, {'name': 'sql'}]}])
def test_invalid_manual(body, client):
    assert client.post('/api/requirements/validate', json=body).status_code == 422

def test_cors(client):
    headers = {'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST'}
    assert client.options('/api/requirements/extract', headers=headers).headers['access-control-allow-origin'] == headers['Origin']
    headers['Origin'] = 'https://untrusted.example'
    assert 'access-control-allow-origin' not in client.options('/api/requirements/extract', headers=headers).headers


def test_matching_http_contract(client):
    body={'reviewed':True,'requirements':{'skills':[{'name':'Python','must':True}]},'candidates':[{'id':'a','text':'Python'}]}
    response=client.post('/api/shortlist/match',json=body)
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    assert response.json()['results'][0]['score']==100
    body['reviewed']=False
    assert client.post('/api/shortlist/match',json=body).status_code==422
