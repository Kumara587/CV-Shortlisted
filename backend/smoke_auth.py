"""Live local auth smoke check. Creates and removes only its own synthetic account."""
import secrets
import httpx
from store import open_store
from encryption import verify_fields

def main():
    store=open_store()
    email='auth-smoke-'+secrets.token_hex(8)+'@example.invalid'
    password=secrets.token_urlsafe(24)+'Aa1!'
    headers={'Origin':'http://127.0.0.1:5173','X-CSRF-Protection':'1'}
    owner=None
    try:
        with httpx.Client(base_url='http://127.0.0.1:8000',headers=headers,timeout=20) as client:
            if client.get('/api/auth/config').json().get('password_reset_available'):
                raise RuntimeError('This smoke test is local/no-SMTP only; no emails were sent.')
            r=client.post('/api/auth/signup',json={'email':email,'first_name':'Synthetic','last_name':'Auth Check','dob':'1995-06-15','password':password,'confirm_password':password})
            if r.status_code!=200:raise RuntimeError('Signup failed: '+str(r.status_code))
            account=store.auth_account(email)
            owner=account['id']
            assert client.get('/api/session').json()['user']['email']==email
            assert client.get('/api/jobs').json()=={'jobs':[]}
            assert client.post('/api/auth/logout',json={}).status_code==200
            assert client.get('/api/session').status_code==401
            assert client.post('/api/auth/login',json={'email':email,'password':password}).status_code==200
            assert client.get('/api/session').status_code==200
            client.post('/api/auth/logout',json={})
        with store.connection() as db:verify_fields(db,store.cipher)
        print('Live PostgreSQL signup, cookie session, isolation, logout, login and encryption: passed.')
    finally:
        if owner:
            with store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM auth_tokens WHERE owner=?',(owner,))
                db.execute('DELETE FROM auth_sessions WHERE owner=?',(owner,))
                db.execute('DELETE FROM auth_accounts WHERE id=? AND email=?',(owner,email))
                db.execute('DELETE FROM users WHERE id=? AND name=?',(owner,'account_'+owner))
            print('Synthetic smoke account removed; existing accounts unchanged.')

if __name__=='__main__':main()
