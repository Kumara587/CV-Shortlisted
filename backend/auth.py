"""Email/password, expiring cookie sessions, recovery and verified Google identity."""
import asyncio
import hmac
import json
import os
from pathlib import Path
import re
import smtplib
import sqlite3
import ssl
import string
from datetime import date
from email.message import EmailMessage
from urllib.parse import urlsplit
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError,InvalidHashError
from fastapi import APIRouter,HTTPException,Request,Response,BackgroundTasks
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator
from starlette.concurrency import run_in_threadpool

router=APIRouter(prefix='/api/auth')
COOKIE='cv_session'
NONCE_COOKIE='cv_google_nonce'
hasher=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=1)
DUMMY_HASH=hasher.hash('dummy-password-never-an-account')
slots=asyncio.Semaphore(2)
GENERIC_RESET='If an eligible account exists, a password reset link will be sent to that email.'


def configuration():
    path=Path(os.getenv('AUTH_CONFIG_FILE',str(Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.config')))/'CVShortlisted'/'secrets'/'auth.credentials.json')))
    if not path.exists():return {}
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value,dict):raise ValueError()
        return value
    except (OSError,ValueError):raise HTTPException(503,'Authentication configuration is unavailable.') from None


def google_client():return str(configuration().get('google_client_id','')).strip()
def mail_ready():
    c=configuration()
    return bool(c.get('smtp_host') and c.get('smtp_from') and c.get('app_url'))


def password_hash(password):return hasher.hash(password)
def validate_password(value):
    if not (8<=len(value)<=128 and re.search(r'[A-Z]',value) and re.search(r'[a-z]',value)
            and re.search(r'[0-9]',value) and any(c in string.punctuation for c in value)):
        raise ValueError('Use 8+ characters with uppercase, lowercase, a number and a special character.')
    return value
def password_matches(encoded,password):
    try:return hasher.verify(encoded or DUMMY_HASH,password) and bool(encoded)
    except (VerificationError,InvalidHashError):return False


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class EmailInput(Input):
    email: str=Field(min_length=3,max_length=254)
    @field_validator('email')
    @classmethod
    def email_address(cls,value):
        value=value.strip().casefold()
        if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}",value):raise ValueError('Invalid email address')
        return value

class Login(EmailInput):
    password: str=Field(min_length=1,max_length=128)

class Signup(Login):
    first_name: str=Field(min_length=1,max_length=50)
    last_name: str=Field(min_length=1,max_length=50)
    dob: date
    confirm_password: str=Field(min_length=1,max_length=128)
    @field_validator('password')
    @classmethod
    def strong_password(cls,value):
        return validate_password(value)
    @field_validator('first_name','last_name')
    @classmethod
    def clean_name(cls,value):
        value=value.strip()
        if not value or any(ord(c)<32 for c in value):raise ValueError('Invalid name')
        return value
    @field_validator('dob')
    @classmethod
    def valid_dob(cls,value):
        if value>date.today():raise ValueError('Date of birth cannot be in the future')
        return value
    @model_validator(mode='after')
    def passwords_match(self):
        if self.password!=self.confirm_password:raise ValueError('Passwords do not match')
        return self

class Reset(Input):
    token: str=Field(min_length=40,max_length=100)
    password: str=Field(min_length=8,max_length=128)
    @field_validator('password')
    @classmethod
    def strong_password(cls,value):return validate_password(value)

class Verify(Input):
    token: str=Field(min_length=40,max_length=100)

class Google(Input):
    credential: str=Field(min_length=100,max_length=12000)


def cookie(response,name,value,request,max_age=43200):
    response.set_cookie(name,value,max_age=max_age,httponly=True,secure=request.app.state.settings.production,samesite='lax',path='/')


def establish(request,response,owner):
    store=request.app.state.store
    previous=request.cookies.get(COOKIE)
    if previous:store.end_session(previous)
    cookie(response,COOKIE,store.new_session(owner),request)
    return {'user':store.auth_profile(owner),'authenticated':True}


def send_email(email,token,purpose,allowed_origins):
    config=configuration()
    app_url=str(config.get('app_url','')).rstrip('/')
    parsed=urlsplit(app_url)
    if app_url not in allowed_origins or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('Invalid configured application origin')
    sender=str(config.get('smtp_from',''))
    if any(c in sender+email for c in '\r\n'):raise ValueError('Invalid email headers')
    link=app_url+'/#'+('reset' if purpose=='reset' else 'verify')+'='+token
    message=EmailMessage()
    message['From']=sender;message['To']=email
    message['Subject']='Reset your Shortlist Studio password' if purpose=='reset' else 'Verify your Shortlist Studio email'
    message.set_content(('Reset your password' if purpose=='reset' else 'Verify your email')+' using this link:\n\n'+link+'\n\nThis link expires in 30 minutes and can be used once. If you did not request it, ignore this email.')
    port=int(config.get('smtp_port',587))
    transport=smtplib.SMTP_SSL if port==465 else smtplib.SMTP
    kwargs={'host':config['smtp_host'],'port':port,'timeout':12}
    if port==465:kwargs['context']=ssl.create_default_context()
    with transport(**kwargs) as smtp:
        if port!=465:smtp.starttls(context=ssl.create_default_context())
        if config.get('smtp_username'):smtp.login(config['smtp_username'],config.get('smtp_password',''))
        smtp.send_message(message)


@router.get('/config')
def config():
    return {'google_client_id':google_client(),'password_reset_available':mail_ready()}


@router.post('/signup')
async def signup(body:Signup,request:Request,response:Response):
    if request.app.state.settings.production and not mail_ready():raise HTTPException(503,'Email verification must be configured before public registration.')
    async with slots:
        encoded=await run_in_threadpool(password_hash,body.password)
        store=request.app.state.store
        try:owner=await run_in_threadpool(store.register_account,body.email,body.first_name+' '+body.last_name,encoded,
            profile={'first_name':body.first_name,'last_name':body.last_name,'dob':body.dob.isoformat()})
        except sqlite3.IntegrityError:raise HTTPException(409,'Unable to create this account. Try signing in or recovering your password.') from None
        if mail_ready():
            token=store.new_auth_token(owner,'verify')
            try:await run_in_threadpool(send_email,body.email,token,'verify',request.app.state.settings.origins)
            except Exception:raise HTTPException(503,'Account created, but verification email delivery failed. Use Resend verification after email delivery is configured.') from None
            return {'verification_required':True,'message':'Check your inbox to verify your email, then sign in.'}
        result=establish(request,response,owner)
        result['message']='Local development account created. Email verification will be required when email delivery is configured.'
        return result


@router.post('/login')
async def login(body:Login,request:Request,response:Response):
    async with slots:
        account=await run_in_threadpool(request.app.state.store.auth_account,body.email)
        valid=await run_in_threadpool(password_matches,account['password_hash'] if account else None,body.password)
        if not valid or not account or not account['active']:raise HTTPException(401,'Email or password is incorrect.')
        if (request.app.state.settings.production or mail_ready()) and not account['email_verified']:
            raise HTTPException(403,'Verify your email before signing in. You can resend the verification email below.')
        return await run_in_threadpool(establish,request,response,account['id'])


@router.post('/logout')
def logout(request:Request,response:Response):
    token=request.cookies.get(COOKIE)
    if token:request.app.state.store.end_session(token)
    response.delete_cookie(COOKIE,path='/',secure=request.app.state.settings.production,httponly=True,samesite='lax')
    return {'signed_out':True}


@router.post('/forgot-password')
@router.post('/resend-verification')
async def forgot(body:EmailInput,request:Request,background_tasks:BackgroundTasks):
    if not mail_ready():raise HTTPException(503,'Email delivery is not configured yet. Password recovery will be available after SMTP setup.')
    store=request.app.state.store
    account=await run_in_threadpool(store.auth_account,body.email)
    purpose='verify' if request.url.path.endswith('resend-verification') else 'reset'
    if account and account['active'] and (purpose!='verify' or not account['email_verified']):
        token=store.new_auth_token(account['id'],purpose)
        def deliver():
            try:send_email(body.email,token,purpose,request.app.state.settings.origins)
            except Exception:
                # Never disclose account existence or log recipient, password, token or SMTP errors.
                from security import log
                log.error('event=auth_email_delivery_failed')
        # Send after the uniform response rather than leaking SMTP latency/account existence.
        background_tasks.add_task(deliver)
    await asyncio.sleep(0.4)
    return {'message':GENERIC_RESET if purpose=='reset' else 'If verification is needed, an email will be sent.'}


@router.post('/reset-password')
async def reset_password(body:Reset,request:Request):
    async with slots:
        encoded=await run_in_threadpool(password_hash,body.password)
        if not await run_in_threadpool(request.app.state.store.consume_account_token,body.token,'reset',encoded):
            raise HTTPException(400,'Reset link is invalid or expired. Request a new link.')
    return {'message':'Password updated. Sign in with your new password. Previous sessions have been signed out.'}


@router.post('/verify-email')
def verify_email(body:Verify,request:Request):
    if not request.app.state.store.consume_account_token(body.token,'verify'):raise HTTPException(400,'Verification link is invalid or expired.')
    return {'message':'Email verified. You can now sign in.'}


@router.post('/google/nonce')
def google_nonce(request:Request,response:Response):
    if not google_client():raise HTTPException(503,'Google sign-in is not configured yet.')
    nonce=request.app.state.store.new_auth_token(None,'google',300)
    cookie(response,NONCE_COOKIE,nonce,request,300)
    return {'nonce':nonce}


def verify_google(credential,client):
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.id_token import verify_oauth2_token
    class BoundedRequest(GoogleRequest):
        def __call__(self,*args,**kwargs):
            kwargs['timeout']=10
            return super().__call__(*args,**kwargs)
    return verify_oauth2_token(credential,BoundedRequest(),client)


@router.post('/google')
async def google_login(body:Google,request:Request,response:Response):
    client=google_client()
    if not client:raise HTTPException(503,'Google sign-in is not configured yet.')
    async with slots:
        try:claims=await run_in_threadpool(verify_google,body.credential,client)
        except Exception:raise HTTPException(401,'Google sign-in could not be verified. Try again.') from None
        nonce=request.cookies.get(NONCE_COOKIE,'')
        if not nonce or not hmac.compare_digest(str(claims.get('nonce','')),nonce):raise HTTPException(401,'Google sign-in session expired. Try again.')
        store=request.app.state.store
        if not store.consume_google_nonce(nonce):raise HTTPException(401,'Google sign-in session expired. Try again.')
        response.delete_cookie(NONCE_COOKIE,path='/')
        if claims.get('email_verified') is not True or not claims.get('sub'):raise HTTPException(401,'Google email must be verified.')
        try:email=EmailInput(email=claims.get('email','')).email
        except ValueError:raise HTTPException(401,'Google email could not be verified.') from None
        account=store.auth_account(email)
        if account:
            if not account['active']:raise HTTPException(401,'Account is unavailable.')
            # Never silently attach a Google identity to an existing password/legacy user.
            if account['google_sub']!=claims['sub']:raise HTTPException(409,'This email already has an account. Sign in using your password.')
            owner=account['id']
        else:
            # Google is authoritative for Gmail/Workspace. Other addresses require our email verification.
            authoritative=email.endswith('@gmail.com') or bool(claims.get('hd'))
            if not authoritative and not mail_ready():raise HTTPException(503,'Email verification must be configured for this Google email address.')
            try:owner=store.register_account(email,str(claims.get('name','Google user'))[:100],google_sub=claims['sub'],verified=authoritative)
            except sqlite3.IntegrityError:raise HTTPException(409,'Account exists. Try signing in again.') from None
            if not authoritative:
                token=store.new_auth_token(owner,'verify')
                try:await run_in_threadpool(send_email,email,token,'verify',request.app.state.settings.origins)
                except Exception:raise HTTPException(503,'Verification email delivery failed. Try Resend verification.') from None
                return {'verification_required':True,'message':'Verify your email using the link in your inbox, then sign in with Google again.'}
        profile=store.auth_profile(owner)
        if not profile['email_verified']:raise HTTPException(403,'Verify your email before signing in. Use Resend verification.')
        return establish(request,response,owner)
