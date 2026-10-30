"""Shared PostgreSQL/SQLite authentication schema and repository methods."""
import hashlib
import secrets
import json

AUTH_SCHEMA='''
CREATE TABLE IF NOT EXISTS auth_accounts(id TEXT PRIMARY KEY REFERENCES users(id),
 email TEXT UNIQUE NOT NULL, password_hash TEXT, google_sub TEXT UNIQUE,
 display_name TEXT NOT NULL, email_verified INTEGER NOT NULL DEFAULT 0,
 created DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS auth_sessions(id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id),
 expires DOUBLE PRECISION NOT NULL, created DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS auth_sessions_owner ON auth_sessions(owner);
CREATE TABLE IF NOT EXISTS auth_tokens(id TEXT PRIMARY KEY, owner TEXT REFERENCES users(id),
 purpose TEXT NOT NULL, expires DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS auth_tokens_owner ON auth_tokens(owner,purpose);
'''

def digest(value):return hashlib.sha256(value.encode()).hexdigest()

class AuthRepository:
    def auth_account(self,email):
        with self.connection() as db:
            row=db.execute('SELECT a.*,u.active FROM auth_accounts a JOIN users u ON u.id=a.id WHERE a.email=?',(email,)).fetchone()
            return dict(row) if row else None

    def register_account(self,email,name,password_hash=None,google_sub=None,verified=False,owner=None,profile=None):
        uid=owner or secrets.token_hex(16)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if not owner:
                # Password/Google users never receive or use this legacy random credential.
                db.execute('INSERT INTO users(id,name,token_hash) VALUES(?,?,?)',(uid,'account_'+uid,digest(secrets.token_urlsafe(48))))
            elif not db.execute('SELECT id FROM users WHERE id=? AND active=1',(owner,)).fetchone():
                raise ValueError('Existing active user not found')
            db.execute('INSERT INTO auth_accounts(id,email,password_hash,google_sub,display_name,email_verified,created) VALUES(?,?,?,?,?,?,?)',
                (uid,email,password_hash,google_sub,self.seal(json.dumps({'version':1,'name':name,**profile}) if profile else name,'auth_accounts','display_name',uid,uid),int(verified),self.clock()))
        return uid

    def auth_profile(self,owner):
        with self.connection() as db:
            row=db.execute('SELECT * FROM auth_accounts WHERE id=?',(owner,)).fetchone()
            if not row:return None
            name=self.unseal(row['display_name'],'auth_accounts','display_name',owner,owner)
            profile={}
            try:
                data=json.loads(name)
                if isinstance(data,dict) and data.get('version')==1:
                    name=data['name']
                    profile={key:data.get(key) for key in ('first_name','last_name','dob')}
            except (ValueError,KeyError,TypeError):pass
            return {'email':row['email'],'name':name,'email_verified':bool(row['email_verified']),**profile}

    def new_session(self,owner):
        token=secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM auth_sessions WHERE expires<=?',(self.clock(),))
            if db.execute('SELECT count(*) FROM auth_sessions WHERE owner=?',(owner,)).fetchone()[0]>=10:
                old=db.execute('SELECT id FROM auth_sessions WHERE owner=? ORDER BY created,id LIMIT 1',(owner,)).fetchone()
                db.execute('DELETE FROM auth_sessions WHERE id=?',(old['id'],))
            db.execute('INSERT INTO auth_sessions(id,owner,expires,created) VALUES(?,?,?,?)',(digest(token),owner,self.clock()+43200,self.clock()))
        return token

    def authenticate_session(self,token):
        if not isinstance(token,str) or not 40<=len(token)<=100:return None
        with self.connection() as db:
            row=db.execute('SELECT s.owner FROM auth_sessions s JOIN users u ON u.id=s.owner WHERE s.id=? AND s.expires>? AND u.active=1',(digest(token),self.clock())).fetchone()
            return row['owner'] if row else None

    def end_session(self,token):
        with self.connection() as db:db.execute('DELETE FROM auth_sessions WHERE id=?',(digest(token),))

    def new_auth_token(self,owner,purpose,ttl=1800):
        token=secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM auth_tokens WHERE expires<=?',(self.clock(),))
            if owner:db.execute('DELETE FROM auth_tokens WHERE owner=? AND purpose=?',(owner,purpose))
            db.execute('INSERT INTO auth_tokens(id,owner,purpose,expires) VALUES(?,?,?,?)',(digest(token),owner,purpose,self.clock()+ttl))
        return token

    def consume_google_nonce(self,token):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT id FROM auth_tokens WHERE id=? AND purpose=? AND expires>?',(digest(token),'google',self.clock())).fetchone()
            if not row:return False
            db.execute('DELETE FROM auth_tokens WHERE id=?',(digest(token),))
            return True

    def consume_account_token(self,token,purpose,password_hash=None):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT t.owner FROM auth_tokens t JOIN users u ON u.id=t.owner WHERE t.id=? AND t.purpose=? AND t.expires>? AND u.active=1',(digest(token),purpose,self.clock())).fetchone()
            if not row:return False
            owner=row['owner']
            if purpose=='reset':
                db.execute('UPDATE auth_accounts SET password_hash=?,email_verified=1 WHERE id=?',(password_hash,owner))
                db.execute('DELETE FROM auth_sessions WHERE owner=?',(owner,))
                # Disable any legacy bearer credential after account recovery.
                db.execute('UPDATE users SET token_hash=? WHERE id=?',(digest(secrets.token_urlsafe(48)),owner))
                db.execute('DELETE FROM auth_tokens WHERE owner=?',(owner,))
            else:
                db.execute('UPDATE auth_accounts SET email_verified=1 WHERE id=?',(owner,))
                db.execute('DELETE FROM auth_tokens WHERE id=?',(digest(token),))
            return True
