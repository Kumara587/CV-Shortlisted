"""Upload orchestration tests with a synchronous coroutine driver.
Real HTTP/process transport coverage lives in test_upload.py.
"""
import asyncio
import json
import subprocess
import sys
from contextlib import nullcontext
from unittest.mock import AsyncMock
import pytest
import main
from parsing import MAX_BYTES

class Request:
    def __init__(self, data=b'Ada Python', headers=None):
        self.data = data
        self.headers = headers or {'content-type': 'text/plain'}
    async def stream(self):
        for i in range(0,len(self.data),65536):
            yield self.data[i:i+65536]

class Process:
    returncode = 0
    async def communicate(self, data):
        result = subprocess.run([sys.executable,'parse_worker.py','a.txt','text/plain'], input=data, capture_output=True, timeout=12)
        return result.stdout, b''

# All mocked awaitables complete immediately, so no socket/event loop is needed.
def run(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as finished:
        return finished.value
    raise AssertionError('Unexpected suspension')

@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(main.asyncio, 'timeout', lambda _: AsyncContext())
    monkeypatch.setattr(main.asyncio, 'create_subprocess_exec', AsyncMock(return_value=Process()))
    async def wait(awaitable, timeout):
        return await awaitable
    monkeypatch.setattr(main.asyncio, 'wait_for', wait)
    monkeypatch.setattr(main, 'parse_slots', asyncio.Semaphore(2))

class AsyncContext:
    async def __aenter__(self): return self
    async def __aexit__(self,*args): return False

def test_route_success(setup):
    response = run(main.parse_resume(Request(), '../../a.txt'))
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert json.loads(response.body)['text'] == 'Ada Python'

@pytest.mark.parametrize('headers,data', [({'content-length':str(MAX_BYTES+1)}, b'x'), ({'content-length':'invalid'},b'x'), ({},b'x'*(MAX_BYTES+1))], ids=['declared-large','bad-length','stream-limit'])
def test_route_size(setup,headers,data):
    response = run(main.parse_resume(Request(data,headers), 'a.txt'))
    assert response.status_code == 413
    assert json.loads(response.body)['error']['code'] == 'too_large'

def test_busy(setup,monkeypatch):
    monkeypatch.setattr(main,'parse_slots',asyncio.Semaphore(0))
    assert run(main.parse_resume(Request(),'a.txt')).status_code == 429

def test_timeout(setup,monkeypatch):
    class Slow(Process):
        returncode = None
        killed = False
        async def communicate(self,data): raise TimeoutError()
        def kill(self): self.killed = True
        async def wait(self): self.returncode = -1
    process = Slow()
    monkeypatch.setattr(main.asyncio,'create_subprocess_exec',AsyncMock(return_value=process))
    response=run(main.parse_resume(Request(),'a.txt'))
    assert json.loads(response.body)['error']['code'] == 'timeout'
    assert process.killed

def test_worker_failure(setup,monkeypatch):
    process=Process()
    process.returncode=1
    monkeypatch.setattr(main.asyncio,'create_subprocess_exec',AsyncMock(return_value=process))
    assert json.loads(run(main.parse_resume(Request(),'a.txt')).body)['error']['code'] == 'parser_failed'
