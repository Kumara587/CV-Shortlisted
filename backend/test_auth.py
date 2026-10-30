"""Account/session/recovery tests with isolated encrypted databases and fake mail/Google."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from encryption import Cipher,verify_fields
from store import Store
from main import create_app
from security import Settings
import auth

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.sqlite3',cipher=Cipher([Fernet.generate_key()]))
        self.config={}
        self.patch=patch('auth.configuration',side_effect=lambda:self.config)
        self.patch.start()
        self.client=TestClient(create_app(self.store,Settings()),base_url='http://127.0.0.1:8000')
        self.headers={'Origin':'http://127.0.0.1:5173','X-CSRF-Protection':'1'}
        self.password='Fictional-test-password-123!'

    def tearDown(self):
        self.client.close();self.patch.stop();self.tmp.cleanup()

    def post(self,path,body=None):return self.client.post('/api/auth/'+path,json=body or {},headers=self.headers)
    def signup(self,email='fictional@example.com'):
        return self.post('signup',{'first_name':'Fictional','last_name':'User','dob':'1995-06-15','email':email,'password':self.password,'confirm_password':self.password})

    def test_signup_session_refresh_and_logout(self):
        r=self.signup();self.assertEqual(r.status_code,200,r.text)
        self.assertNotIn('token',r.text)
        self.assertIn('HttpOnly',r.headers['set-cookie']);self.assertIn('SameSite=lax',r.headers['set-cookie'])
        self.assertEqual(self.client.get('/api/session').status_code,200)
        profile=self.client.get('/api/session').json()['user']
        self.assertEqual(profile['first_name'],'Fictional')
        self.assertEqual(profile['last_name'],'User')
        self.assertEqual(profile['dob'],'1995-06-15')
        self.assertEqual(self.client.get('/api/jobs').json(),{'jobs':[]})
        cookie=self.client.cookies.get('cv_session')
        with self.store.connection() as db:
            row=db.execute('SELECT password_hash,display_name FROM auth_accounts').fetchone()
            self.assertTrue(row[0].startswith('$argon2id$'))
            self.assertTrue(row[1].startswith('enc:v1:'))
            self.assertNotEqual(db.execute('SELECT id FROM auth_sessions').fetchone()[0],cookie)
            self.assertEqual(verify_fields(db,self.store.cipher),1)
        self.assertEqual(self.post('logout').status_code,200)
        self.assertEqual(self.client.get('/api/session').status_code,401)
        self.assertIsNone(self.store.authenticate_session(cookie))
        self.assertEqual(self.post('login',{'email':'FICTIONAL@example.com','password':self.password}).status_code,200)

    def test_csrf_invalid_password_and_duplicate_account(self):
        self.assertEqual(self.client.post('/api/auth/signup',json={'name':'F','email':'fake@example.com','password':self.password}).status_code,403)
        self.assertEqual(self.signup().status_code,200)
        self.assertEqual(self.signup().status_code,409)
        self.post('logout')
        self.assertEqual(self.post('login',{'email':'fictional@example.com','password':'wrong'}).status_code,401)
        self.assertEqual(self.post('login',{'email':'missing@example.com','password':'wrong'}).status_code,401)
        self.assertEqual(self.post('signup',{'name':'F','email':'fake@example.com','password':'short'}).status_code,422)
        self.assertEqual(self.client.post('/api/auth/login',json={},headers={'Origin':'https://evil.invalid','X-CSRF-Protection':'1'}).status_code,403)

    def test_session_expiry_and_account_revocation(self):
        self.signup();token=self.client.cookies.get('cv_session')
        self.store.clock=lambda:10**12
        self.assertIsNone(self.store.authenticate_session(token))
        self.assertEqual(self.client.get('/api/jobs').status_code,401)

    def test_reset_is_single_use_revokes_sessions_and_does_not_auto_login(self):
        self.signup();old=self.client.cookies.get('cv_session')
        account=self.store.auth_account('fictional@example.com')
        token=self.store.new_auth_token(account['id'],'reset')
        new='New-fictional-password-456!'
        self.assertEqual(self.post('reset-password',{'token':token,'password':new}).status_code,200)
        self.assertIsNone(self.store.authenticate_session(old))
        self.assertEqual(self.client.get('/api/session').status_code,401)
        self.assertEqual(self.post('reset-password',{'token':token,'password':new}).status_code,400)
        self.assertEqual(self.post('login',{'email':account['email'],'password':self.password}).status_code,401)
        self.assertEqual(self.post('login',{'email':account['email'],'password':new}).status_code,200)

    def test_mail_delivery_and_verification_tokens_never_return_to_browser(self):
        self.config.update({'smtp_host':'smtp.example.invalid','smtp_from':'noreply@example.com','app_url':'http://127.0.0.1:5173'})
        deliveries=[]
        with patch('auth.send_email',side_effect=lambda email,token,purpose,origins:deliveries.append((token,purpose))):
            result=self.signup()
            self.assertTrue(result.json()['verification_required'])
            self.assertEqual(self.client.get('/api/session').status_code,401)
            token,purpose=deliveries.pop();self.assertEqual(purpose,'verify');self.assertNotIn(token,result.text)
            self.assertEqual(self.post('verify-email',{'token':token}).status_code,200)
            self.assertEqual(self.post('verify-email',{'token':token}).status_code,400)
            self.assertEqual(self.post('login',{'email':'fictional@example.com','password':self.password}).status_code,200)
            existing=self.post('forgot-password',{'email':'fictional@example.com'})
            missing=self.post('forgot-password',{'email':'unknown@example.com'})
            self.assertEqual(existing.json(),missing.json())
            self.assertNotIn(deliveries[0][0],existing.text)

    def test_unconfigured_external_services_are_explicit(self):
        self.assertFalse(self.client.get('/api/auth/config').json()['password_reset_available'])
        self.assertEqual(self.post('forgot-password',{'email':'fictional@example.com'}).status_code,503)
        self.assertEqual(self.post('google/nonce').status_code,503)

    def test_google_nonce_verified_identity_and_replay_rejection(self):
        self.config['google_client_id']='fictional.apps.googleusercontent.com'
        nonce=self.post('google/nonce').json()['nonce']
        claims={'sub':'fictional-sub','email':'fake@gmail.com','email_verified':True,'name':'Fake Google User','nonce':nonce}
        with patch('auth.verify_google',return_value=claims):
            response=self.post('google',{'credential':'x'*120})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(self.client.get('/api/session').json()['user']['email'],'fake@gmail.com')
            self.client.cookies.set('cv_google_nonce',nonce,domain='127.0.0.1',path='/')
            self.assertEqual(self.post('google',{'credential':'x'*120}).status_code,401)

    def test_google_never_silently_links_existing_password_account(self):
        self.signup();self.post('logout')
        self.config['google_client_id']='fictional.apps.googleusercontent.com'
        nonce=self.post('google/nonce').json()['nonce']
        with patch('auth.verify_google',return_value={'sub':'other-sub','email':'fictional@example.com','email_verified':True,'nonce':nonce}):
            self.assertEqual(self.post('google',{'credential':'x'*120}).status_code,409)
        self.assertEqual(self.client.get('/api/session').status_code,401)

    def test_legacy_user_can_be_attached_without_changing_owner(self):
        uid,token=self.store.create_user('legacy-recruiter')
        self.store.register_account('legacy@example.com','Legacy Recruiter',auth.password_hash(self.password),owner=uid)
        self.assertEqual(self.store.authenticate(token),uid)
        self.assertEqual(self.post('login',{'email':'legacy@example.com','password':self.password}).status_code,200)
        self.assertEqual(self.store.authenticate_session(self.client.cookies.get('cv_session')),uid)

    def test_encrypted_backup_restore_preserves_accounts(self):
        from storage_admin import backup,restore
        self.signup()
        destination=Path(self.tmp.name)/'accounts.cvbackup'
        restored=Path(self.tmp.name)/'restored.sqlite3'
        backup(self.store,destination)
        self.assertNotIn(b'fictional@example.com',destination.read_bytes())
        restore(destination,restored,self.store.cipher)
        target=Store(restored,cipher=self.store.cipher)
        account=target.auth_account('fictional@example.com')
        self.assertTrue(auth.password_matches(account['password_hash'],self.password))
        self.assertEqual(target.auth_profile(account['id'])['name'],'Fictional User')

    def test_reset_expiry_and_production_cookie_flags(self):
        self.signup()
        account=self.store.auth_account('fictional@example.com')
        token=self.store.new_auth_token(account['id'],'reset',ttl=1)
        original=self.store.clock
        self.store.clock=lambda:original()+2
        self.assertEqual(self.post('reset-password',{'token':token,'password':'Different-password-123!'}).status_code,400)
        self.config.update({'smtp_host':'smtp.example.invalid','smtp_from':'noreply@example.com','app_url':'https://workspace.example'})
        with self.store.connection() as db:db.execute('UPDATE auth_accounts SET email_verified=1 WHERE id=?',(account['id'],))
        settings=Settings(production=True,origins=('https://workspace.example',),hosts=('workspace.example',))
        with TestClient(create_app(self.store,settings),base_url='https://workspace.example') as client:
            r=client.post('/api/auth/login',json={'email':account['email'],'password':self.password},headers={'Origin':'https://workspace.example','X-CSRF-Protection':'1'})
            self.assertEqual(r.status_code,200,r.text)
            self.assertIn('Secure',r.headers['set-cookie'])

    def test_google_invalid_signature_and_wrong_nonce_are_rejected(self):
        self.config['google_client_id']='fictional.apps.googleusercontent.com'
        self.post('google/nonce')
        with patch('auth.verify_google',side_effect=ValueError('Invalid signature')):
            self.assertEqual(self.post('google',{'credential':'x'*120}).status_code,401)
        with patch('auth.verify_google',return_value={'nonce':'wrong','email_verified':True,'sub':'fake','email':'fake@gmail.com'}):
            self.assertEqual(self.post('google',{'credential':'x'*120}).status_code,401)
        self.assertEqual(self.client.get('/api/session').status_code,401)

    def test_signup_password_rules_confirmation_and_dob(self):
        from pydantic import ValidationError
        from datetime import date,timedelta
        valid={'first_name':' Test ','last_name':' User ','dob':'2000-01-01','email':'rules@example.com','password':'Abcd12!x','confirm_password':'Abcd12!x'}
        parsed=auth.Signup.model_validate(valid)
        self.assertEqual(parsed.first_name,'Test')
        for password in ['Ab1!','abcdef1!','ABCDEF1!','Abcdefg!','Abcdef12']:
            with self.subTest(password_rule=password),self.assertRaises(ValidationError):
                auth.Signup.model_validate({**valid,'password':password,'confirm_password':password})
        for change in [{'confirm_password':'Wrong123!'}, {'dob':(date.today()+timedelta(days=1)).isoformat()}, {'dob':'2025-02-30'}, {'first_name':'   '}, {'last_name':''}]:
            with self.subTest(field=list(change)),self.assertRaises(ValidationError):auth.Signup.model_validate({**valid,**change})
        self.assertEqual(self.post('signup',valid).status_code,200)
        with self.store.connection() as db:
            stored=db.execute('SELECT display_name FROM auth_accounts').fetchone()[0]
            self.assertNotIn('2000-01-01',stored)

if __name__=='__main__':unittest.main()
