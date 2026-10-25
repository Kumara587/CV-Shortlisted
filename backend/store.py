"""Owner-scoped short-lived export snapshots. Raw CVs/evidence are never stored."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

class MissingSnapshot(Exception): pass

class Store:
    def __init__(self, path, ttl=3600, clock=time.time):
        self.path=Path(path)
        self.ttl=ttl
        self.clock=clock

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not self.path.exists():
            try:
                fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                os.close(fd)
            except FileExistsError:
                pass
        db=sqlite3.connect(self.path,timeout=5)
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA foreign_keys=ON')
            db.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, token_hash TEXT UNIQUE NOT NULL, active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS snapshots_owner ON snapshots(owner);''')
            yield db
            db.commit()
        finally:
            db.close()

    def create_user(self,name):
        token=secrets.token_urlsafe(32)
        uid=secrets.token_hex(16)
        with self.connection() as db:
            db.execute('INSERT INTO users(id,name,token_hash) VALUES(?,?,?)',(uid,name,hashlib.sha256(token.encode()).hexdigest()))
        return uid,token

    def revoke(self,name):
        with self.connection() as db:
            row=db.execute('SELECT id FROM users WHERE name=?',(name,)).fetchone()
            if row:
                db.execute('UPDATE users SET active=0 WHERE id=?',(row['id'],))
                db.execute('DELETE FROM snapshots WHERE owner=?',(row['id'],))
            return bool(row)

    def authenticate(self,token):
        if not 40<=len(token)<=100: return None
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.connection() as db:
            row=db.execute('SELECT id FROM users WHERE token_hash=? AND active=1',(digest,)).fetchone()
            return row['id'] if row else None

    def purge(self):
        with self.connection() as db:
            return db.execute('DELETE FROM snapshots WHERE expires<=?',(self.clock(),)).rowcount

    def save(self,owner,results,labels):
        snapshot=secrets.token_urlsafe(24)
        expires=self.clock()+self.ttl
        # All scoring values originate from the server, not an export request.
        payload=[{'id':r['id'],'rank':r['rank'],'label':labels.get(r['id'],r['id']), 'score':r['score'],'group':r['group'],'review_status':'pending', 'supported_skills':[s['name'] for s in r['skills'] if s['status']=='supported'], 'missing_or_uncertain':r['missing_or_uncertain'], 'must_have_issues':[s['name'] for s in r['must_have_issues']]} for r in results]
        with self.connection() as db:
            db.execute('DELETE FROM snapshots WHERE expires<=?',(self.clock(),))
            # Bound retained sensitive state for each account.
            if db.execute('SELECT count(*) FROM snapshots WHERE owner=?',(owner,)).fetchone()[0]>=20:
                old=db.execute('SELECT id FROM snapshots WHERE owner=? ORDER BY expires,id LIMIT 1',(owner,)).fetchone()
                db.execute('DELETE FROM snapshots WHERE id=?',(old['id'],))
            db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',(snapshot,owner,expires,json.dumps(payload,ensure_ascii=True)))
        return snapshot,expires

    def get(self,owner,snapshot):
        self.purge()
        with self.connection() as db:
            row=db.execute('SELECT payload,expires FROM snapshots WHERE id=? AND owner=?',(snapshot,owner)).fetchone()
            if not row: raise MissingSnapshot()
            return json.loads(row['payload']),row['expires']

    def review(self,owner,snapshot,candidate,status):
        # One transaction prevents concurrent reviews losing each other's updates.
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT payload FROM snapshots WHERE id=? AND owner=? AND expires>?',(snapshot,owner,self.clock())).fetchone()
            if not row: raise MissingSnapshot()
            payload=json.loads(row['payload'])
            target=next((r for r in payload if r['id']==candidate),None)
            if target is None: raise MissingSnapshot()
            target['review_status']=status
            db.execute('UPDATE snapshots SET payload=? WHERE id=? AND owner=?',(json.dumps(payload,ensure_ascii=True),snapshot,owner))

    def delete(self,owner,snapshot=None):
        with self.connection() as db:
            if snapshot is None:
                return db.execute('DELETE FROM snapshots WHERE owner=?',(owner,)).rowcount
            count=db.execute('DELETE FROM snapshots WHERE id=? AND owner=?',(snapshot,owner)).rowcount
            if not count: raise MissingSnapshot()
            return count
