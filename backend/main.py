"""Authenticated parsing/matching API with owned, expiring export summaries."""
import os
import re
from typing import Literal

from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from typing_extensions import Annotated
from matching import prohibited_requirement, rank_candidates

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Skill(StrictModel):
    name: Text
    must: bool = False

class Requirements(StrictModel):
    skills: list[Skill] = Field(default_factory=list, max_length=100)
    minimum_years: float | None = Field(default=None, ge=0, le=60, allow_inf_nan=False)
    education: Literal['', 'Diploma', 'Bachelor', 'Master', 'PhD'] = ''

    @model_validator(mode='after')
    def unique_skills(self):
        if any(prohibited_requirement(s.name) for s in self.skills):
            raise ValueError('Requirements must describe job qualifications, not protected or personal attributes')
        names = [s.name.casefold() for s in self.skills]
        if len(names) != len(set(names)):
            raise ValueError('Skill names must be unique')
        return self

class ExtractionRequest(StrictModel):
    job_description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=20000)]

class ExtractionResponse(StrictModel):
    requirements: Requirements
    method: Literal['deterministic_fallback'] = 'deterministic_fallback'
    warnings: list[str]

SKILLS = ['React', 'JavaScript', 'TypeScript', 'SQL', 'MySQL', 'REST API', 'Git', 'Excel', 'Jira', 'Communication', 'Manual Testing', 'Automation Testing', 'Selenium', 'QA', 'API Testing', 'Python', 'Java', 'Kubernetes', 'Leadership', 'Figma', 'Node.js', 'C++', 'C#', 'AWS', 'Docker', 'FastAPI']

def extract(text: str) -> Requirements:
    skills = [Skill(name=s) for s in SKILLS if re.search(r'(?<!\w)' + re.escape(s) + r'(?!\w)', text, re.I)]
    # Require experience context; do not interpret company age or graduation years.
    matches = re.findall(r'(?<![\w.])(\d{1,3}(?:\.\d{1,2})?)\s*(?:[-–]\s*\d{1,3}(?:\.\d{1,2})?)?\+?\s*years?\s+(?:of\s+)?(?:(?:relevant|practical|professional|work|software|development)\s+){0,3}experience', text, re.I)
    years = min((float(n) for n in matches if float(n) <= 60), default=None)
    degrees = [('Diploma', r'\bdiploma\b'), ('Bachelor', r"\bbachelor(?:'s)?\b|\bb\.?sc\b|\bundergraduate\b"), ('Master', r"\bmaster(?:'s)?\b|\bm\.?sc\b"), ('PhD', r'\bph\.?d\b|\bdoctorate\b')]
    education = next((name for name, pattern in degrees if re.search(pattern, text, re.I)), '')
    return Requirements(skills=skills, minimum_years=years, education=education)

router = APIRouter()

async def validation_error(request, exc):
    # Pydantic's default errors echo inputs; keep potentially sensitive text out.
    return JSONResponse(status_code=422, headers={'Cache-Control': 'no-store'}, content={'detail': [{'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]})

@router.get('/health')
async def health():
    return {'status': 'ok', 'version': '0.4.0'}

@router.post('/api/requirements/extract', response_model=ExtractionResponse)
async def extract_requirements(body: ExtractionRequest):
    return ExtractionResponse(requirements=extract(body.job_description), warnings=['Rule-based extraction, not AI. Review skills, education and experience; alternatives, negations and preferences may be misinterpreted. Must-have flags require manual review.'])

@router.post('/api/requirements/validate', response_model=Requirements)
async def validate_requirements(body: Requirements):
    return body

# One raw-file request avoids multipart temporary-file spooling.
import asyncio
import json
import sys
from pathlib import Path
from fastapi import Request, Header
from urllib.parse import unquote
from parsing import MAX_BYTES, failure, safe_name

parse_slots = asyncio.Semaphore(2)

@router.post('/api/resumes/parse')
async def parse_resume(request: Request, filename: str = Header(alias='X-Filename', min_length=1, max_length=1024)):
    filename = unquote(filename)
    name = safe_name(filename)
    ext = name.rsplit('.', 1)[-1].lower()
    headers = {'Cache-Control': 'no-store', 'Pragma': 'no-cache', 'X-Content-Type-Options': 'nosniff'}
    def reply(result, status=200):
        return JSONResponse(result, status_code=status, headers=headers)
    if parse_slots.locked():
        return reply(failure(name, ext, 'busy', 'Parser is busy. Retry this file shortly.'), 429)
    length = request.headers.get('content-length')
    if length and (len(length) > 10 or not length.isdecimal() or int(length) > MAX_BYTES):
        return reply(failure(name, ext, 'too_large', 'File exceeds 5 MB or has an invalid length.'), 413)
    async with parse_slots:
        data = bytearray()
        process = None
        try:
            async with asyncio.timeout(15):
                async for chunk in request.stream():
                    if len(data) + len(chunk) > MAX_BYTES:
                        return reply(failure(name, ext, 'too_large', 'File exceeds 5 MB.'), 413)
                    data.extend(chunk)
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(Path(__file__).with_name('parse_worker.py')),
                name, request.headers.get('content-type', '')[:200],
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},
            )
            stdout, _ = await asyncio.wait_for(process.communicate(bytes(data)), timeout=12)
            if process.returncode:
                return reply(failure(name, ext, 'parser_failed', 'Parser stopped unexpectedly. Try a fresh export or paste text.'))
            result = json.loads(stdout)
            return reply(result)
        except TimeoutError:
            return reply(failure(name, ext, 'timeout', 'Upload or parsing timed out. Split the document or paste text.'))
        except asyncio.CancelledError:
            raise
        except Exception:
            return reply(failure(name, ext, 'parser_failed', 'Could not process this file. Retry or paste text.'))
        finally:
            data.clear()
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()


class CandidateInput(StrictModel):
    id: Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')]
    text: str = Field(max_length=200000)
    display_label: Annotated[str, StringConstraints(max_length=160)] = ''
    parse_status: Literal['parsed', 'needs_text', 'error'] = 'parsed'
    warnings: list[Annotated[str, StringConstraints(max_length=500)]] = Field(default_factory=list, max_length=10)

class MatchRequest(StrictModel):
    requirements: Requirements
    reviewed: Literal[True]
    candidates: list[CandidateInput] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({c.id for c in self.candidates}) != len(self.candidates):
            raise ValueError('Candidate IDs must be unique')
        return self

@router.post('/api/shortlist/match')
async def match_shortlist(body: MatchRequest, request: Request):
    result=rank_candidates(body.requirements, body.candidates)
    snapshot,expires=request.app.state.store.save(request.state.user_id,result['results'],{c.id:c.display_label or c.id for c in body.candidates})
    result.update(snapshot_id=snapshot,expires_at=expires)
    return JSONResponse(result, headers={'Cache-Control':'no-store', 'Pragma':'no-cache'})


from contextlib import asynccontextmanager
from fastapi.responses import Response
from security import Settings, install_security
from store import Store, MissingSnapshot
from exporting import export_csv

@router.get('/api/session')
async def session(request: Request):
    return {'authenticated':True,'retention_seconds':request.app.state.settings.ttl}

class ReviewUpdate(StrictModel):
    candidate_id: Annotated[str, StringConstraints(min_length=1,max_length=64,pattern=r'^[A-Za-z0-9_-]+$')]
    status: Literal['pending','reviewed','shortlisted','not_progressing']

@router.patch('/api/shortlists/{snapshot}/reviews')
async def update_review(snapshot: str, body: ReviewUpdate, request: Request):
    try: request.app.state.store.review(request.state.user_id,snapshot,body.candidate_id,body.status)
    except MissingSnapshot: raise HTTPException(404,'Shortlist not found or expired')
    return {'saved':True}

@router.get('/api/shortlists/{snapshot}/export')
async def download_export(snapshot: str, request: Request, blind: bool=True):
    try: rows,_=request.app.state.store.get(request.state.user_id,snapshot)
    except MissingSnapshot: raise HTTPException(404,'Shortlist not found or expired')
    return Response(export_csv(rows,blind),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="shortlist.csv"','Cache-Control':'no-store'})

@router.delete('/api/shortlists/{snapshot}')
async def delete_snapshot(snapshot: str, request: Request):
    try: request.app.state.store.delete(request.state.user_id,snapshot)
    except MissingSnapshot: raise HTTPException(404,'Shortlist not found or expired')
    return Response(status_code=204)

@router.delete('/api/shortlists')
async def delete_all_snapshots(request: Request):
    count=request.app.state.store.delete(request.state.user_id)
    return {'deleted':count}

@asynccontextmanager
async def lifecycle(api):
    api.state.store.purge()
    async def cleanup():
        while True:
            await asyncio.sleep(30)
            try: api.state.store.purge()
            except Exception:
                from security import log
                log.error('event=cleanup_failed route=maintenance status=500')
    task=asyncio.create_task(cleanup())
    try: yield
    finally:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

def create_app(store=None,settings=None):
    settings=settings or Settings.environment()
    store=store or Store(Path(os.getenv('SCREENER_DATA_DIR',str(Path(__file__).parent/'data')))/'screener.sqlite3',settings.ttl)
    api=FastAPI(title='Resume Screener API',version='0.4.0',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifecycle)
    api.state.store=store
    api.state.settings=settings
    api.include_router(router)
    api.add_exception_handler(RequestValidationError,validation_error)
    install_security(api,store,settings)
    return api

app=create_app()
