"""Actual ASGI authentication/body pipeline plus a real disposable parser process."""
import subprocess
import sys
from unittest.mock import AsyncMock
from test_security import secured
from test_parsing import docx,pdf


def test_upload_endpoint(secured,monkeypatch):
    client=secured[1]
    class Process:
        def __init__(self,args): self.args=args;self.returncode=None
        async def communicate(self,data):
            result=subprocess.run(self.args,input=data,capture_output=True,timeout=15)
            self.returncode=result.returncode
            return result.stdout,b''
    async def create(*args,**kwargs): return Process(args)
    async def wait(awaitable,timeout): return await awaitable
    monkeypatch.setattr('main.asyncio.create_subprocess_exec',create)
    monkeypatch.setattr('main.asyncio.wait_for',wait)
    for data,filename in [(b'Ada Python','a.txt'),(pdf(),'a.pdf'),(docx(),'a.docx')]:
        r=client.request('POST','/api/resumes/parse',raw=data,headers={'content-type':'application/octet-stream','x-filename':filename})
        assert r.status_code==200 and r.json()['status']=='parsed',r.text
        assert r.headers['cache-control']=='no-store'
    r=client.request('POST','/api/resumes/parse',raw=b'broken',headers={'x-filename':'a.pdf'})
    assert r.json()['error']['code']=='type_mismatch'
    r=client.request('POST','/api/resumes/parse',raw=b'x',headers={'x-filename':'a.txt','content-length':str(5*1024*1024+1)})
    assert r.status_code==413
    assert client.request('POST','/api/resumes/parse',raw=b'x').status_code==422
