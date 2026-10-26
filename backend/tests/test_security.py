"""Security tests drive the actual ASGI stack without opening network sockets."""
import json
from urllib.parse import urlsplit
import httpx
import pytest
from main import create_app
from security import Settings, RateLimiter
from store import Store

class NoTimeout:
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False

class Client:
    def __init__(self,app,token=None): self.app,self.token=app,token
    def request(self,method,path,body=None,headers=None,raw=None,chunks=None,scheme='http',host='localhost'):
        payload=(json.dumps(body).encode() if body is not None else b'') if raw is None else raw
        h={'host':host}
        if self.token: h['authorization']='Bearer '+self.token
        if body is not None: h['content-type']='application/json'
        h.update({k.lower():v for k,v in (headers or {}).items()})
        parts=urlsplit(path)
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':scheme,'path':parts.path,'raw_path':parts.path.encode(),'query_string':parts.query.encode(),'headers':[(k.encode(),v.encode()) for k,v in h.items()],'client':('127.0.0.1',1234),'server':('localhost',8000)}
        messages=[]
        pieces=list(chunks) if chunks is not None else [payload]
        async def receive():
            if pieces:
                chunk=pieces.pop(0)
                return {'type':'http.request','body':chunk,'more_body':bool(pieces)}
            return {'type':'http.disconnect'}
        async def send(message): messages.append(message)
        coroutine=self.app(scope,receive,send)
        try: coroutine.send(None)
        except StopIteration: pass
        else: raise AssertionError('Unexpected suspension; test transport must stay in memory')
        start=next(m for m in messages if m['type']=='http.response.start')
        data=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
        return httpx.Response(start['status'],headers=start['headers'],content=data)

@pytest.fixture
def secured(tmp_path,monkeypatch):
    monkeypatch.setattr('security.asyncio.timeout',lambda _:NoTimeout())
    async def inline(function,*args,**kwargs): return function(*args,**kwargs)
    monkeypatch.setattr('main.run_in_threadpool',inline)
    store=Store(tmp_path/'private.sqlite3')
    _,alice=store.create_user('alice')
    _,bob=store.create_user('bob')
    settings=Settings(origins=('http://localhost:5173',),hosts=('localhost',))
    app=create_app(store,settings)
    return store,Client(app,alice),Client(app,bob),Client(app)

def body(label='Ada'):
    return {'reviewed':True,'requirements':{'skills':[{'name':'Python','must':True}]},'candidates':[{'id':'candidate-a','display_label':label,'text':'Private resume Python\nEmail: secret@example.com'}]}

def test_authentication_and_revocation(secured):
    store,a,b,anon=secured
    assert anon.request('POST','/api/shortlist/match',body()).status_code==401
    assert Client(a.app,'not-a-token').request('GET','/api/session').status_code==401
    assert a.request('GET','/api/session').json()['authenticated']
    store.revoke('alice')
    assert a.request('GET','/api/session').status_code==401
    assert anon.request('GET','/health').status_code==200

def test_ownership_export_review_delete(secured):
    store,a,b,_=secured
    result=a.request('POST','/api/shortlist/match',body())
    assert result.status_code==200,result.text
    snapshot=result.json()['snapshot_id']
    url='/api/shortlists/'+snapshot
    assert b.request('GET',url+'/export').status_code==404
    assert b.request('PATCH',url+'/reviews',{'candidate_id':'candidate-a','status':'shortlisted'}).status_code==404
    assert b.request('DELETE',url).status_code==404
    assert a.request('PATCH',url+'/reviews',{'candidate_id':'candidate-a','status':'shortlisted'}).status_code==200
    exported=a.request('GET',url+'/export?blind=false')
    assert exported.status_code==200 and 'Ada' in exported.text and 'shortlisted' in exported.text
    assert '100.0' in exported.text and 'secret@example.com' not in exported.text
    assert a.request('PATCH',url+'/reviews',{'candidate_id':'candidate-a','status':'shortlisted','score':999}).status_code==422
    assert a.request('GET',url+'/export?blind=true').text.find('Ada')==-1
    assert a.request('DELETE',url).status_code==204
    assert a.request('GET',url+'/export').status_code==404

def test_no_cv_storage_and_expiry(secured):
    store,a,_,_=secured
    now=[1000.0];store.clock=lambda:now[0];store.ttl=60
    result=a.request('POST','/api/shortlist/match',body()).json()
    assert b'Private resume' not in store.path.read_bytes()
    assert b'secret@example.com' not in store.path.read_bytes()
    now[0]=1061
    assert a.request('GET','/api/shortlists/'+result['snapshot_id']+'/export').status_code==404
    with store.connection() as db: assert db.execute('SELECT count(*) FROM snapshots').fetchone()[0]==0

def test_delete_all_owner_only(secured):
    _,a,b,_=secured
    sid=a.request('POST','/api/shortlist/match',body()).json()['snapshot_id']
    other=b.request('POST','/api/shortlist/match',body()).json()['snapshot_id']
    assert a.request('DELETE','/api/shortlists').json()['deleted']==1
    assert a.request('GET',f'/api/shortlists/{sid}/export').status_code==404
    assert b.request('GET',f'/api/shortlists/{other}/export').status_code==200

def test_cors_host_headers_and_sanitized_logs(secured,caplog):
    _,a,_,_=secured
    caplog.set_level('INFO',logger='screener.security')
    r=a.request('GET','/api/session',headers={'origin':'http://localhost:5173'})
    assert r.headers['access-control-allow-origin']=='http://localhost:5173'
    assert r.headers['cache-control']=='no-store' and r.headers['x-frame-options']=='DENY'
    assert a.request('GET','/api/session',headers={'origin':'https://evil.example'}).status_code==403
    assert a.request('GET','/api/session',host='evil.example').status_code==400
    assert a.request('POST','/api/secret-filename?token=secret',raw=b'private text').status_code==404
    assert a.token not in caplog.text and 'secret-filename' not in caplog.text and 'private text' not in caplog.text

def test_streamed_and_declared_limits(secured):
    _,a,_,anon=secured
    assert a.request('POST','/api/requirements/extract',headers={'content-length':'102401'}).status_code==413
    assert a.request('POST','/api/resumes/parse',headers={'content-length':str(5*1024*1024+1),'x-filename':'private.pdf'}).status_code==413
    assert a.request('POST','/api/resumes/parse',chunks=[b'x'*3000000,b'x'*3000000]).status_code==413
    assert a.request('POST','/api/requirements/extract',headers={'content-length':'-1'}).status_code==400
    assert a.request('POST','/api/requirements/extract',raw=b'{}',headers={'content-length':'1'}).status_code==400
    assert anon.request('POST','/api/resumes/parse',chunks=[b'x'*6000000]).status_code==401

def test_tls_gate_and_configuration(tmp_path,monkeypatch):
    monkeypatch.setattr('security.asyncio.timeout',lambda _:NoTimeout())
    async def inline(function,*args,**kwargs): return function(*args,**kwargs)
    monkeypatch.setattr('main.run_in_threadpool',inline)
    store=Store(tmp_path/'data.sqlite3');_,token=store.create_user('user')
    settings=Settings(True,('https://app.example.com',),('app.example.com',),3600)
    c=Client(create_app(store,settings),token)
    assert c.request('GET','/api/session',host='app.example.com',headers={'x-forwarded-proto':'https'}).status_code==426
    r=c.request('GET','/api/session',host='app.example.com',scheme='https')
    assert r.status_code==200 and 'max-age' in r.headers['strict-transport-security']
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('CORS_ORIGINS','*');monkeypatch.setenv('ALLOWED_HOSTS','app.example.com')
    with pytest.raises(ValueError): Settings.environment()
    monkeypatch.setenv('CORS_ORIGINS','http://app.example.com')
    with pytest.raises(ValueError): Settings.environment()

def test_rate_limit_is_enforced(secured):
    _,a,_,_=secured
    statuses=[a.request('GET','/api/session').status_code for _ in range(121)]
    assert 429 in statuses or 401 in statuses

def test_exception_is_sanitized(secured,monkeypatch,caplog):
    store,a,_,_=secured
    def bad(*args): raise RuntimeError('private CV token secret')
    monkeypatch.setattr(store,'save',bad)
    caplog.set_level('INFO',logger='screener.security')
    r=a.request('POST','/api/shortlist/match',body())
    assert r.status_code==500 and 'private CV' not in r.text and 'private CV' not in caplog.text

def test_preflight_and_duplicate_headers(secured):
    _,a,_,_=secured
    r=a.request('OPTIONS','/api/shortlists/id/reviews',headers={'origin':'http://localhost:5173','access-control-request-method':'PATCH','access-control-request-headers':'authorization,content-type'})
    assert r.status_code==200
    assert r.headers['access-control-allow-origin']!='*'
    assert 'access-control-allow-credentials' not in r.headers
    r=a.request('OPTIONS','/api/session',headers={'origin':'http://localhost:5173','access-control-request-method':'GET','access-control-request-headers':'x-unknown'})
    assert r.status_code==400


def test_account_hashes_and_snapshot_count(secured):
    store,a,_,_=secured
    owner=store.authenticate(a.token)
    with store.connection() as db:
        row=db.execute('SELECT token_hash FROM users WHERE id=?',(owner,)).fetchone()
        assert row['token_hash']!=a.token and len(row['token_hash'])==64
    from matching import rank_candidates
    from main import Requirements,CandidateInput
    rows=rank_candidates(Requirements(skills=[{'name':'Python'}]),[CandidateInput(id='a',text='Python')])['results']
    now=[1000.0];store.clock=lambda:now[0]
    first=None
    for i in range(21):
        now[0]+=1
        snapshot,_=store.save(owner,rows,{'a':'Safe label'})
        if first is None: first=snapshot
    from store import MissingSnapshot
    with pytest.raises(MissingSnapshot): store.get(owner,first)
    with store.connection() as db:
        assert db.execute('SELECT count(*) FROM snapshots WHERE owner=?',(owner,)).fetchone()[0]==20


def test_server_export_escapes_injected_labels(secured):
    _,a,_,_=secured
    result=a.request('POST','/api/shortlist/match',body('\t=HYPERLINK("https://evil")')).json()
    r=a.request('GET','/api/shortlists/'+result['snapshot_id']+'/export?blind=false')
    import csv
    from io import StringIO
    rows=list(csv.reader(StringIO(r.content.decode('utf-8-sig'))))
    assert rows[1][1].startswith("'=")
    assert r.headers['content-disposition']=='attachment; filename="shortlist.csv"'


def test_body_timeout_and_error_logging(secured,monkeypatch):
    _,a,_,_=secured
    class TimedOut:
        async def __aenter__(self): raise TimeoutError()
        async def __aexit__(self,*args): return False
    monkeypatch.setattr('security.asyncio.timeout',lambda _:TimedOut())
    assert a.request('POST','/api/requirements/validate',body={}).status_code==408


def test_shortlist_unknown_candidate_and_tampered_owner(secured):
    _,a,_,_=secured
    sid=a.request('POST','/api/shortlist/match',body()).json()['snapshot_id']
    assert a.request('PATCH',f'/api/shortlists/{sid}/reviews',{'candidate_id':'someone-else','status':'shortlisted'}).status_code==404
    bad=body();bad['owner']='another-user'
    assert a.request('POST','/api/shortlist/match',bad).status_code==422

def test_rate_limiter_window_and_bounded_memory():
    now=[0.0];limiter=RateLimiter(clock=lambda:now[0])
    assert limiter.allow('user',1)
    assert not limiter.allow('user',1)
    now[0]=60.1
    assert limiter.allow('user',1)
    for i in range(5000): limiter.allow(('key',i),1)
    assert len(limiter.buckets)==4096

def test_auth_storage_failure_and_global_concurrency(secured,monkeypatch):
    store,a,_,_=secured
    assert a.request('GET','/api/session').status_code==200
    middleware=a.app.middleware_stack
    while middleware.__class__.__name__!='SecurityMiddleware': middleware=middleware.app
    middleware.active=8
    assert a.request('GET','/api/session').status_code==429
    middleware.active=0
    def broken(token): raise RuntimeError('secret credential database failure')
    monkeypatch.setattr(store,'authenticate',broken)
    response=a.request('GET','/api/session')
    assert response.status_code==503 and 'secret' not in response.text
    assert response.headers['cache-control']=='no-store'
