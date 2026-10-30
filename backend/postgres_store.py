"""PostgreSQL storage using shared encrypted repository operations."""
from contextlib import contextmanager
from threading import Lock
import sqlite3
import psycopg
from urllib.parse import urlsplit
from store import Store
from encryption import verify_or_initialize, StorageSecurityError
from auth_store import AUTH_SCHEMA

LOCK_ID=731924681
SCHEMA='''
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
 token_hash TEXT UNIQUE NOT NULL, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)));
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id),
 title TEXT NOT NULL, workspace TEXT NOT NULL, created DOUBLE PRECISION NOT NULL, updated DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(owner,updated);
CREATE TABLE IF NOT EXISTS screenings(id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id),
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, document TEXT NOT NULL,
 export_rows TEXT NOT NULL, created DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS screenings_job ON screenings(owner,job_id,created);
CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id),
 expires DOUBLE PRECISION NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS snapshots_owner ON snapshots(owner);
CREATE TABLE IF NOT EXISTS storage_meta(id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL);
'''


class Row:
    """The shared repository supports both positional and named column reads."""
    def __init__(self,columns,values):self.columns=columns;self.values=values
    def __getitem__(self,key):return self.values[key if isinstance(key,(int,slice)) else self.columns.index(key)]
    def keys(self):return self.columns
    def __iter__(self):return iter(self.values)
    def __len__(self):return len(self.values)


class Cursor:
    def __init__(self,cursor):
        self.cursor=cursor
        self.columns=[c.name for c in cursor.description] if cursor.description else []
    @property
    def rowcount(self):return self.cursor.rowcount
    def fetchone(self):
        row=self.cursor.fetchone()
        return Row(self.columns,row) if row is not None else None
    def fetchall(self):return [Row(self.columns,r) for r in self.cursor.fetchall()]
    def __iter__(self):return (Row(self.columns,r) for r in self.cursor)


class Connection:
    """Adapt only our fixed internal SQL, never user-authored SQL strings."""
    def __init__(self,raw):self.raw=raw;self.locked=False
    def lock(self):
        if not self.locked:
            self.raw.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK_ID,))
            self.locked=True
    def execute(self,sql,params=()):
        try:
            if sql.strip().upper() in {'BEGIN IMMEDIATE','BEGIN EXCLUSIVE'}:
                self.lock()
                return Cursor(self.raw.execute('SELECT 1'))
            if sql.lstrip().split()[0].upper() in {'INSERT','UPDATE','DELETE'}:self.lock()
            if sql=='INSERT OR REPLACE INTO storage_meta VALUES(1,?)':
                sql='INSERT INTO storage_meta(id,token) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET token=EXCLUDED.token'
            return Cursor(self.raw.execute(sql.replace('?','%s'),params or None))
        except psycopg.IntegrityError:
            raise sqlite3.IntegrityError('Database integrity constraint failed.') from None
        except psycopg.Error:
            raise sqlite3.OperationalError('PostgreSQL operation failed. Check database availability, permissions and transaction state.') from None
    def commit(self):self.raw.commit();self.locked=False
    def rollback(self):self.raw.rollback();self.locked=False


class PostgresStore(Store):
    dialect='postgresql'
    def __init__(self,url,ttl=3600,clock=None,cipher=None,search_path=None):
        kwargs={'cipher':cipher}
        if clock is not None:kwargs['clock']=clock
        super().__init__('postgresql',ttl,**kwargs)
        self.url=url
        self.search_path=search_path
        self._initialized=False
        self._init_lock=Lock()

    def _connect(self):
        try:
            tls={}
            if (urlsplit(self.url).hostname or '').endswith('.neon.tech'):
                import certifi
                tls={'sslmode':'verify-full','sslrootcert':certifi.where()}
            raw=psycopg.connect(self.url,connect_timeout=5,application_name='cv-shortlisted',
                options='-c statement_timeout=15000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=30000',**tls)
            if self.search_path:
                from psycopg import sql
                raw.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.search_path)))
                raw.commit()
            return raw
        except psycopg.Error:
            raise sqlite3.OperationalError('PostgreSQL connection failed. Check the private connection file and local server.') from None

    def initialize(self,maintenance=False):
        with self._init_lock:
            if self._initialized:return
            cipher=self.cipher
            with self._connect() as raw:
                raw.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK_ID,))
                for statement in (SCHEMA+AUTH_SCHEMA).split(';'):
                    if statement.strip():raw.execute(statement)
                verify_or_initialize(Connection(raw),cipher,maintenance,metadata_ready=True)
            self._initialized=True

    @contextmanager
    def connection(self,maintenance=False):
        self.initialize(maintenance)
        with self._connect() as raw:
            db=Connection(raw)
            verify_or_initialize(db,self.cipher,maintenance,metadata_ready=True)
            db.commit()
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
