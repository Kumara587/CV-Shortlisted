"""Authentication, origin/host/TLS checks, bounded bodies and request throttling."""
from collections import OrderedDict
from dataclasses import dataclass
import asyncio
import logging
import os
import re
import time
from urllib.parse import urlsplit
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

log=logging.getLogger('screener.security')

@dataclass(frozen=True)
class Settings:
    production: bool=False
    origins: tuple=('http://localhost:5173','http://127.0.0.1:5173')
    hosts: tuple=('localhost','127.0.0.1','::1')
    ttl: int=3600

    @classmethod
    def environment(cls):
        mode=os.getenv('APP_ENV','local')
        if mode not in {'local','production'}: raise ValueError('APP_ENV must be local or production')
        production=mode=='production'
        origins=tuple(s.strip() for s in os.getenv('CORS_ORIGINS','' if production else 'http://localhost:5173,http://127.0.0.1:5173').split(',') if s.strip())
        hosts=tuple(s.strip().lower() for s in os.getenv('ALLOWED_HOSTS','' if production else 'localhost,127.0.0.1,::1').split(',') if s.strip())
        if not origins or not hosts: raise ValueError('Explicit origins and hosts are required')
        for origin in origins:
            u=urlsplit(origin)
            if '*' in origin or not u.hostname or u.username or u.password or u.path or u.query or u.fragment or u.scheme not in {'http','https'}:
                raise ValueError('Origins must be exact scheme/host/port origins')
            if production and u.scheme!='https': raise ValueError('Production origins require HTTPS')
            if not production and u.hostname not in {'localhost','127.0.0.1','::1'}: raise ValueError('Local origins must use loopback')
        if any('*' in host or '/' in host or not host for host in hosts): raise ValueError('Allowed hosts must be explicit')
        ttl=int(os.getenv('RETENTION_SECONDS','3600'))
        if not 60<=ttl<=86400: raise ValueError('Retention must be 60..86400 seconds')
        return cls(production,origins,hosts,ttl)


def route_key(path):
    if path=='/api/jobs': return '/api/jobs'
    if re.fullmatch(r'/api/jobs/[A-Za-z0-9_-]+/runs',path): return '/api/jobs/:id/runs'
    if re.fullmatch(r'/api/jobs/[A-Za-z0-9_-]+',path): return '/api/jobs/:id'
    if re.fullmatch(r'/api/screenings/[A-Za-z0-9_-]+',path): return '/api/screenings/:id'
    if path in {'/health','/api/session','/api/requirements/extract','/api/requirements/validate','/api/resumes/parse','/api/shortlist/match','/api/shortlists','/docs','/openapi.json'}: return path
    if re.fullmatch(r'/api/shortlists/[A-Za-z0-9_-]+/export',path): return '/api/shortlists/:id/export'
    if re.fullmatch(r'/api/shortlists/[A-Za-z0-9_-]+/reviews',path): return '/api/shortlists/:id/reviews'
    if re.fullmatch(r'/api/shortlists/[A-Za-z0-9_-]+',path): return '/api/shortlists/:id'
    return 'other'

class RateLimiter:
    def __init__(self,clock=time.monotonic): self.clock=clock;self.buckets=OrderedDict()
    def allow(self,key,limit):
        now=self.clock()
        bucket=self.buckets.get(key)
        if not bucket or now-bucket[0]>=60: bucket=[now,0]
        bucket[1]+=1
        self.buckets[key]=bucket
        self.buckets.move_to_end(key)
        while len(self.buckets)>4096: self.buckets.popitem(last=False)
        return bucket[1]<=limit

class SecurityMiddleware:
    def __init__(self,app,store,settings,limiter=None):
        self.app,self.store,self.settings=app,store,settings
        self.limiter=limiter or RateLimiter()
        self.active=0

    async def __call__(self,scope,receive,send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        route=route_key(scope['path'])
        headers={k.lower():v for k,v in scope.get('headers',[])}
        sent=False
        async def secure_send(message):
            nonlocal sent
            if message['type']=='http.response.start':
                sent=True
                extra=[(b'cache-control',b'no-store'),(b'pragma',b'no-cache'),(b'x-content-type-options',b'nosniff'),(b'x-frame-options',b'DENY'),(b'referrer-policy',b'no-referrer'),(b'content-security-policy',b"default-src 'none'; frame-ancestors 'none'")]
                if self.settings.production: extra.append((b'strict-transport-security',b'max-age=31536000'))
                names={k for k,_ in extra}
                message={**message,'headers':[(k,v) for k,v in message.get('headers',[]) if k.lower() not in names]+extra}
                log.info('event=response route=%s status=%d',route,message['status'])
            await send(message)
        async def reject(status,message):
            response=JSONResponse({'detail':message},status_code=status,headers={'Retry-After':'60'} if status==429 else None)
            await response(scope,receive,secure_send)
        if sum(len(k)+len(v) for k,v in scope.get('headers',[]))>16384:
            return await reject(431,'Request headers too large')
        if any(sum(k.lower()==field for k,_ in scope.get('headers',[]))>1 for field in [b'host',b'authorization',b'origin',b'content-type']):
            return await reject(400,'Ambiguous request headers')
        host=headers.get(b'host',b'').decode('latin1')
        try: hostname=urlsplit('//'+host).hostname
        except ValueError: hostname=None
        if hostname not in self.settings.hosts: return await reject(400,'Host not allowed')
        if self.settings.production and scope.get('scheme')!='https': return await reject(426,'HTTPS required')
        origin=headers.get(b'origin')
        if origin and origin.decode('latin1') not in self.settings.origins: return await reject(403,'Origin not allowed')
        # /health contains no data, but still has a bounded per-IP request rate.
        ip=(scope.get('client') or ('unknown',0))[0]
        if not self.limiter.allow(('ip',ip),180): return await reject(429,'Request rate exceeded')
        if scope['path']!='/health':
            auth=headers.get(b'authorization',b'').decode('latin1')
            if not self.limiter.allow(('auth',ip),120): return await reject(429,'Authentication request limit exceeded')
            if not auth.startswith('Bearer '): return await reject(401,'Authentication required')
            try: owner=self.store.authenticate(auth[7:])
            except Exception: return await reject(503,'Authentication temporarily unavailable')
            if not owner: return await reject(401,'Invalid or revoked access token')
            scope.setdefault('state',{})['user_id']=owner
            limit=10 if route=='/api/resumes/parse' else 20 if route in {'/api/shortlist/match','/api/shortlists/:id/export'} else 120
            if not self.limiter.allow(('owner',owner),120) or not self.limiter.allow(('route',owner,route),limit):
                return await reject(429,'Request rate exceeded')
        body_limit=5*1024*1024 if route=='/api/resumes/parse' else 10*1024*1024 if route in {'/api/shortlist/match','/api/jobs','/api/jobs/:id'} else 100*1024
        lengths=[v for k,v in scope.get('headers',[]) if k.lower()==b'content-length']
        if len(lengths)>1 or (lengths and (not lengths[0].isdigit() or len(lengths[0])>10)):
            return await reject(400,'Invalid content length')
        if lengths and int(lengths[0])>body_limit: return await reject(413,'Request body too large')
        if self.active>=8: return await reject(429,'Concurrent request limit exceeded')
        self.active+=1
        async def bounded_request():
            body=bytearray()
            try:
                async with asyncio.timeout(15):
                    while True:
                        message=await receive()
                        if message['type']=='http.disconnect': return
                        chunk=message.get('body',b'')
                        if len(body)+len(chunk)>body_limit: return await reject(413,'Request body too large')
                        body.extend(chunk)
                        if not message.get('more_body',False): break
            except TimeoutError:
                return await reject(408,'Request body timed out')
            if lengths and int(lengths[0])!=len(body): return await reject(400,'Content length mismatch')
            delivered=False
            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered=True
                    return {'type':'http.request','body':bytes(body),'more_body':False}
                return {'type':'http.disconnect'}
            try:
                await self.app(scope,replay,secure_send)
            except Exception:
                # Do not log exceptions, URLs, filenames, bodies, tokens or user identities.
                if not sent: await reject(500,'Request could not be completed')
            finally:
                body.clear()
        try:
            await bounded_request()
        finally:
            self.active-=1


def install_security(app,store,settings):
    app.add_middleware(SecurityMiddleware,store=store,settings=settings)
    # CORS wraps security responses, including 401/403, but exposes only CSV filename.
    app.add_middleware(CORSMiddleware,allow_origins=list(settings.origins),allow_credentials=False,allow_methods=['GET','POST','PATCH','DELETE'],allow_headers=['Authorization','Content-Type','X-Filename'],expose_headers=['Content-Disposition'],max_age=600)
