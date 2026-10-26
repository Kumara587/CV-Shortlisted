"""Owner-scoped persistent jobs, parsed CVs and versioned screening runs."""
import json
import secrets

MAX_LIBRARY_BYTES = 100 * 1024 * 1024


SCHEMA = '''
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
 workspace TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(owner,updated);
CREATE TABLE IF NOT EXISTS screenings(
 id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id),
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 document TEXT NOT NULL, export_rows TEXT NOT NULL, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS screenings_job ON screenings(owner,job_id,created);
'''


class LibraryLimit(Exception):
    pass


class Library:
    @staticmethod
    def check_library_space(db,owner,added):
        jobs=db.execute('SELECT coalesce(sum(length(workspace)),0) FROM jobs WHERE owner=?',(owner,)).fetchone()[0]
        runs=db.execute('SELECT coalesce(sum(length(document)+length(export_rows)),0) FROM screenings WHERE owner=?',(owner,)).fetchone()[0]
        if jobs+runs+added>MAX_LIBRARY_BYTES: raise LibraryLimit()

    def save_job(self, owner, workspace, job_id=None):
        from store import MissingSnapshot
        now = self.clock()
        title = workspace['title']
        encoded=json.dumps(workspace)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if job_id:
                existing=db.execute('SELECT workspace FROM jobs WHERE id=? AND owner=?',(job_id,owner)).fetchone()
                if not existing:
                    raise MissingSnapshot()
                encrypted=self.seal(encoded,'jobs','workspace',owner,job_id)
                self.check_library_space(db,owner,len(encrypted)-len(existing['workspace']))
                db.execute('UPDATE jobs SET title=?,workspace=?,updated=? WHERE id=? AND owner=?',
                           (self.seal(title,'jobs','title',owner,job_id),encrypted,now,job_id,owner))
            else:
                if db.execute('SELECT count(*) FROM jobs WHERE owner=?',(owner,)).fetchone()[0] >= 100:
                    raise LibraryLimit()
                job_id = 'job_' + secrets.token_urlsafe(24)
                encrypted=self.seal(encoded,'jobs','workspace',owner,job_id)
                self.check_library_space(db,owner,len(encrypted))
                db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',
                           (job_id,owner,self.seal(title,'jobs','title',owner,job_id),encrypted,now,now))
        return self.job(owner,job_id)

    def list_jobs(self,owner):
        with self.connection() as db:
            rows=db.execute('SELECT j.id,j.title,j.created,j.updated,(SELECT count(*) FROM screenings s WHERE s.job_id=j.id AND s.owner=j.owner) AS run_count FROM jobs j WHERE j.owner=? ORDER BY j.updated DESC,j.id',(owner,)).fetchall()
            return [{**dict(row),'title':self.unseal(row['title'],'jobs','title',owner,row['id'])} for row in rows]

    def job(self,owner,job_id):
        from store import MissingSnapshot
        with self.connection() as db:
            row=db.execute('SELECT id,workspace,created,updated FROM jobs WHERE id=? AND owner=?',(job_id,owner)).fetchone()
            if not row: raise MissingSnapshot()
            return {'id':row['id'],'workspace':json.loads(self.unseal(row['workspace'],'jobs','workspace',owner,job_id)),
                    'created':row['created'],'updated':row['updated']}

    def delete_job(self,owner,job_id):
        from store import MissingSnapshot
        with self.connection() as db:
            if not db.execute('DELETE FROM jobs WHERE id=? AND owner=?',(job_id,owner)).rowcount:
                raise MissingSnapshot()

    def save_run(self,owner,job_id,requirements,candidates,result,job_workspace=None):
        from store import MissingSnapshot
        run_id='run_' + secrets.token_urlsafe(24)
        now=self.clock()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT workspace FROM jobs WHERE id=? AND owner=?',(job_id,owner)).fetchone()
            if not row: raise MissingSnapshot()
            if db.execute('SELECT count(*) FROM screenings WHERE job_id=? AND owner=?',(job_id,owner)).fetchone()[0]>=100:
                raise LibraryLimit()
            workspace=dict(job_workspace) if job_workspace is not None else json.loads(self.unseal(row['workspace'],'jobs','workspace',owner,job_id))
            workspace.update(requirements=requirements,candidates=candidates)
            document={'workspace':workspace,'result':result}
            labels={c['id']:c['display_label'] or c['id'] for c in candidates}
            rows=self.export_rows(result['results'],labels)
            encrypted_document=self.seal(json.dumps(document),'screenings','document',owner,run_id)
            encrypted_rows=self.seal(json.dumps(rows),'screenings','export_rows',owner,run_id)
            self.check_library_space(db,owner,len(encrypted_document)+len(encrypted_rows))
            db.execute('INSERT INTO screenings VALUES(?,?,?,?,?,?)',
                       (run_id,owner,job_id,encrypted_document,encrypted_rows,now))
        return run_id

    def list_runs(self,owner,job_id):
        self.job(owner,job_id)
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT id,job_id,created FROM screenings WHERE owner=? AND job_id=? ORDER BY created DESC,id',(owner,job_id))]

    def run(self,owner,run_id):
        from store import MissingSnapshot
        with self.connection() as db:
            row=db.execute('SELECT * FROM screenings WHERE id=? AND owner=?',(run_id,owner)).fetchone()
            if not row: raise MissingSnapshot()
            document=json.loads(self.unseal(row['document'],'screenings','document',owner,run_id))
            return {'id':row['id'],'job_id':row['job_id'],'created':row['created'],**document}

    def run_export(self,owner,run_id):
        from store import MissingSnapshot
        with self.connection() as db:
            row=db.execute('SELECT export_rows FROM screenings WHERE id=? AND owner=?',(run_id,owner)).fetchone()
            if not row: raise MissingSnapshot()
            return json.loads(self.unseal(row['export_rows'],'screenings','export_rows',owner,run_id)),None

    def review_run(self,owner,run_id,candidate,status):
        from store import MissingSnapshot
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT document,export_rows FROM screenings WHERE id=? AND owner=?',(run_id,owner)).fetchone()
            if not row: raise MissingSnapshot()
            document=json.loads(self.unseal(row['document'],'screenings','document',owner,run_id)); rows=json.loads(self.unseal(row['export_rows'],'screenings','export_rows',owner,run_id))
            target=next((r for r in document['result']['results'] if r['id']==candidate),None)
            if target is None: raise MissingSnapshot()
            target['review_status']=status
            for r in rows:
                if r['id']==candidate: r['review_status']=status
            db.execute('UPDATE screenings SET document=?,export_rows=? WHERE id=? AND owner=?',
                       (self.seal(json.dumps(document),'screenings','document',owner,run_id),self.seal(json.dumps(rows),'screenings','export_rows',owner,run_id),run_id,owner))

    def delete_run(self,owner,run_id):
        from store import MissingSnapshot
        with self.connection() as db:
            if not db.execute('DELETE FROM screenings WHERE id=? AND owner=?',(run_id,owner)).rowcount:
                raise MissingSnapshot()
