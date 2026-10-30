"""Authenticated parsing/matching API with owned, expiring export summaries."""
import os
import re
from typing import Literal

from starlette.concurrency import run_in_threadpool
from fastapi import FastAPI, APIRouter, HTTPException, Request
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

from llm_contracts import Criterion as ExtractedCriterion, prohibited_criterion
import llm_service

class Requirements(StrictModel):
    skills: list[Skill] = Field(default_factory=list, max_length=100)
    criteria: list[ExtractedCriterion] = Field(default_factory=list,max_length=100)
    extraction_receipt: str | None = Field(default=None,max_length=20000)
    minimum_years: float | None = Field(default=None, ge=0, le=60, allow_inf_nan=False)
    education: Literal['', 'Diploma', 'Bachelor', 'Master', 'PhD'] = ''

    @model_validator(mode='after')
    def unique_skills(self):
        if any(prohibited_requirement(s.name) for s in self.skills):
            raise ValueError('Requirements must describe job qualifications, not protected or personal attributes')
        if any(prohibited_criterion(c) for c in self.criteria):
            raise ValueError('Criteria must describe job qualifications, not protected or personal attributes')
        if len({c.id for c in self.criteria})!=len(self.criteria):
            raise ValueError('Criterion IDs must be unique')
        names = [s.name.casefold() for s in self.skills]
        if len(names) != len(set(names)):
            raise ValueError('Skill names must be unique')
        return self

class ExtractionRequest(StrictModel):
    synthetic_data_confirmed: bool = False
    job_description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=20000)]

class ExtractionResponse(StrictModel):
    requirements: Requirements
    method: Literal['source_based_extraction']
    warnings: list[str]

from extraction import extract_document


def extract(text: str) -> Requirements:
    return Requirements(**extract_document(text)['requirements'])

router = APIRouter()

async def validation_error(request, exc):
    # Pydantic's default errors echo inputs; keep potentially sensitive text out.
    return JSONResponse(status_code=422, headers={'Cache-Control': 'no-store'}, content={'detail': [{'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]})

@router.get('/health')
async def health():
    return {'status': 'ok', 'version': '0.9.0', 'features': ['saved_jobs', 'screening_history', 'encrypted_storage', 'source_grounded_extraction','llm_evidence_evaluation']}

@router.post('/api/requirements/extract', response_model=ExtractionResponse)
async def extract_requirements(body: ExtractionRequest):
    result=await run_in_threadpool(extract_document,body.job_description)
    return ExtractionResponse(**result)

def criteria_fingerprint(criteria):
    import hashlib
    import json
    return hashlib.sha256(json.dumps([c.model_dump() for c in criteria],sort_keys=True).encode()).hexdigest()


def verify_extraction_receipt(requirements,request):
    if not requirements.extraction_receipt: return {'status':'manual_or_legacy_criteria'}
    try:
        import json
        raw=request.app.state.store.unseal(requirements.extraction_receipt,'ai','extraction',request.state.user_id,'v1')
        receipt=json.loads(raw)
        return {'status':'verified' if receipt['criteria_sha256']==criteria_fingerprint(requirements.criteria) else 'reviewed_edits',
                'original_versions':receipt['versions']}
    except Exception:
        return {'status':'unverified_receipt'}


@router.post('/api/ai/requirements/extract')
async def extract_ai_requirements(body: ExtractionRequest,request: Request):
    try: llm_service.require_data_confirmation(body.synthetic_data_confirmed)
    except llm_service.AIInputError as exc: raise HTTPException(422,detail={'code':'ai_input','message':str(exc)})
    if match_slots.locked(): raise HTTPException(429,'AI evaluation is busy. Retry shortly.')
    async with match_slots:
        try: result=await run_in_threadpool(llm_service.extract_job,body.job_description)
        except llm_service.AIUnavailable as exc: raise HTTPException(503,detail={'code':'ai_unavailable','message':str(exc)})
        except llm_service.AIInputError as exc: raise HTTPException(422,detail={'code':'ai_input','message':str(exc)})
    import json
    requirements=Requirements(**result['requirements'])
    requirements.extraction_receipt=request.app.state.store.seal(json.dumps({
        'criteria_sha256':criteria_fingerprint(requirements.criteria),'versions':result['versions']}),
        'ai','extraction',request.state.user_id,'v1')
    result['requirements']=requirements.model_dump()
    return result


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
match_slots = asyncio.Semaphore(1)

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
    synthetic_data_confirmed: bool = False
    job_id: Annotated[str, StringConstraints(pattern=r'^job_[A-Za-z0-9_-]+$',max_length=64)] | None = None
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
    return await execute_match(body,request,False)


@router.post('/api/ai/shortlist/match')
async def match_ai_shortlist(body: MatchRequest,request: Request):
    try: llm_service.require_data_confirmation(body.synthetic_data_confirmed)
    except llm_service.AIInputError as exc: raise HTTPException(422,detail={'code':'ai_input','message':str(exc)})
    return await execute_match(body,request,True)


async def execute_match(body,request,ai):
    store=request.app.state.store
    job_workspace=None
    if body.job_id:
        try: job_workspace=store.job(request.state.user_id,body.job_id)['workspace']
        except MissingSnapshot: raise HTTPException(404,'Saved job not found')
    if match_slots.locked():
        raise HTTPException(429, 'Matching is busy. Retry shortly.')
    async with match_slots:
        if ai:
            try: result=await run_in_threadpool(llm_service.evaluate,body.requirements,body.candidates)
            except llm_service.AIUnavailable as exc: raise HTTPException(503,detail={'code':'ai_unavailable','message':str(exc)})
            except llm_service.AIInputError as exc: raise HTTPException(422,detail={'code':'ai_input','message':str(exc)})
            result['versions']['extraction_provenance']=verify_extraction_receipt(body.requirements,request)
        else:
            result=await run_in_threadpool(rank_candidates, body.requirements, body.candidates)
    if body.job_id:
        try:
            snapshot=store.save_run(request.state.user_id,body.job_id,body.requirements.model_dump(),
                                    [c.model_dump() for c in body.candidates],result,job_workspace)
        except MissingSnapshot: raise HTTPException(404,'Saved job not found')
        except LibraryLimit: raise HTTPException(409,'Saved storage limit reached. Delete an old job or screening.')
        expires=None
    else:
        snapshot,expires=store.save(request.state.user_id,result['results'],{c.id:c.display_label or c.id for c in body.candidates})
    result.update(snapshot_id=snapshot,expires_at=expires)
    return JSONResponse(result, headers={'Cache-Control':'no-store', 'Pragma':'no-cache'})


from contextlib import asynccontextmanager
from fastapi.responses import Response
from security import Settings, install_security
from store import Store, MissingSnapshot, open_store
from exporting import export_csv
from library import LibraryLimit


class JobWorkspace(StrictModel):
    title: Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=160)]
    job_description: str = Field(default='',max_length=20000)
    requirements: Requirements
    candidates: list[CandidateInput] = Field(default_factory=list,max_length=10)

    @model_validator(mode='after')
    def unique_candidates(self):
        if len({c.id for c in self.candidates}) != len(self.candidates):
            raise ValueError('Candidate IDs must be unique')
        return self


@router.get('/api/jobs')
async def list_jobs(request: Request):
    return {'jobs':request.app.state.store.list_jobs(request.state.user_id)}


@router.post('/api/jobs',status_code=201)
async def create_job(body: JobWorkspace,request: Request):
    try: return request.app.state.store.save_job(request.state.user_id,body.model_dump())
    except LibraryLimit: raise HTTPException(409,'Saved storage limit reached. Delete an old job or screening.')


@router.get('/api/jobs/{job_id}')
async def get_job(job_id: str,request: Request):
    try: return request.app.state.store.job(request.state.user_id,job_id)
    except MissingSnapshot: raise HTTPException(404,'Saved job not found')


@router.patch('/api/jobs/{job_id}')
async def update_job(job_id: str,body: JobWorkspace,request: Request):
    try: return request.app.state.store.save_job(request.state.user_id,body.model_dump(),job_id)
    except MissingSnapshot: raise HTTPException(404,'Saved job not found')
    except LibraryLimit: raise HTTPException(409,'Saved storage limit reached. Delete an old job or screening.')


@router.delete('/api/jobs/{job_id}')
async def delete_job(job_id: str,request: Request):
    try: request.app.state.store.delete_job(request.state.user_id,job_id)
    except MissingSnapshot: raise HTTPException(404,'Saved job not found')
    return Response(status_code=204)


@router.get('/api/jobs/{job_id}/runs')
async def list_runs(job_id: str,request: Request):
    try: return {'runs':request.app.state.store.list_runs(request.state.user_id,job_id)}
    except MissingSnapshot: raise HTTPException(404,'Saved job not found')


@router.get('/api/screenings/{run_id}')
async def get_run(run_id: str,request: Request):
    try: return request.app.state.store.run(request.state.user_id,run_id)
    except MissingSnapshot: raise HTTPException(404,'Screening not found')


@router.delete('/api/screenings/{run_id}')
async def delete_run(run_id: str,request: Request):
    try: request.app.state.store.delete_run(request.state.user_id,run_id)
    except MissingSnapshot: raise HTTPException(404,'Screening not found')
    return Response(status_code=204)

@router.get('/api/session')
async def session(request: Request):
    return {'authenticated':True,'retention_seconds':request.app.state.settings.ttl,'ai_configured':llm_service.configured(),'database':request.app.state.store.dialect,'user':request.app.state.store.auth_profile(request.state.user_id)}

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
    store=store or open_store(settings.ttl)
    api=FastAPI(title='Resume Screener API',version='0.9.0',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifecycle)
    api.state.store=store
    api.state.settings=settings
    api.include_router(router)
    from auth import router as auth_router
    api.include_router(auth_router)
    api.add_exception_handler(RequestValidationError,validation_error)
    install_security(api,store,settings)
    return api

app=create_app()
