"""Verified ciphertext-preserving cutover and portable encrypted PG backups."""
import json
from pathlib import Path
from encryption import private_write,verify_fields,StorageSecurityError
from storage_admin import backup_connection,read_backup
from store import Store,default_database_file

TABLES={
 'users':('id','name','token_hash','active'),
 'jobs':('id','owner','title','workspace','created','updated'),
 'screenings':('id','owner','job_id','document','export_rows','created'),
 'snapshots':('id','owner','expires','payload'),
 'storage_meta':('id','token'),
 'auth_accounts':('id','email','password_hash','google_sub','display_name','email_verified','created'),
 'auth_sessions':('id','owner','expires','created'),
 'auth_tokens':('id','owner','purpose','expires'),
}
MAGIC=b'CVPGBACKUP1\n'


def rows(db):
    return {table:[list(row) for row in db.execute(f"SELECT {','.join(columns)} FROM {table} ORDER BY id")]
            for table,columns in TABLES.items()}


def import_rows(target,data):
    legacy=set(TABLES)-{'auth_accounts','auth_sessions','auth_tokens'}
    if set(data)==legacy:data={**data,'auth_accounts':[],'auth_sessions':[],'auth_tokens':[]}
    if set(data)!=set(TABLES):raise StorageSecurityError('Backup table set is invalid.')
    with target.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        existing=rows(db)
        if any(existing[t] for t in TABLES if t!='storage_meta'):
            if existing==data:
                verify_fields(db,target.cipher)
                return {t:len(r) for t,r in data.items()}
            raise StorageSecurityError('Target database contains records. Migration/restore never overwrites existing data.')
        db.execute('DELETE FROM storage_meta')
        for table,columns in TABLES.items():
            for row in data[table]:
                if not isinstance(row,list) or len(row)!=len(columns):raise StorageSecurityError('Backup row structure is invalid.')
                db.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",row)
        if rows(db)!=data:raise StorageSecurityError('Database copy verification failed; target transaction rolled back.')
        verify_fields(db,target.cipher)
    return {t:len(r) for t,r in data.items()}


def migrate_sqlite(source_path,target,backup_path):
    if not Path(source_path).is_file():raise StorageSecurityError('SQLite source file does not exist.')
    source=Store(source_path,cipher=target.cipher)
    with source.connection() as db:
        verify_fields(db,source.cipher)
        version=db.execute('PRAGMA data_version').fetchone()[0]
        backup_connection(db,source.cipher,backup_path)
        db.execute('BEGIN IMMEDIATE')
        if db.execute('PRAGMA data_version').fetchone()[0]!=version:
            raise StorageSecurityError('Source changed during backup. Stop the backend and retry with a fresh backup path.')
        data=rows(db)
        return import_rows(target,data)


def backup_postgres(store,destination):
    with store.connection() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        verify_fields(db,store.cipher)
        data=rows(db)
    write_backup(data,store.cipher,destination)


def write_backup(data,cipher,destination):
    payload=json.dumps({'format':'cv-postgres-v1','tables':data},ensure_ascii=True).encode()
    encrypted=MAGIC+cipher.encrypt_bytes(payload)
    private_write(destination,encrypted)
    if load_backup(destination,cipher)!=data:
        raise StorageSecurityError('Written PostgreSQL backup failed verification.')


def migrate_postgres(source,target,backup_path):
    """Freeze cooperating writers; back up and verify an exact ciphertext copy."""
    if source.url==target.url:raise StorageSecurityError('Source and target must differ.')
    with source.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        verify_fields(db,source.cipher)
        data=rows(db)
        write_backup(data,source.cipher,backup_path)
        counts=import_rows(target,data)
        if rows(db)!=data:raise StorageSecurityError('Source changed during migration; activation was not performed.')
        return counts


def load_backup(path,cipher):
    raw=Path(path).read_bytes()
    if raw.startswith(MAGIC):
        try:
            payload=json.loads(cipher.decrypt_bytes(raw[len(MAGIC):]))
            if payload['format']!='cv-postgres-v1':raise ValueError()
            data=payload['tables']
            legacy=set(TABLES)-{'auth_accounts','auth_sessions','auth_tokens'}
            if set(data)==legacy:data={**data,'auth_accounts':[],'auth_sessions':[],'auth_tokens':[]}
            if set(data)!=set(TABLES):raise ValueError()
            return data
        except (ValueError,KeyError,TypeError):
            raise StorageSecurityError('PostgreSQL recovery backup is invalid.') from None
    memory=read_backup(path,cipher)
    try:
        from auth_store import AUTH_SCHEMA
        memory.executescript(AUTH_SCHEMA)
        verify_fields(memory,cipher)
        return rows(memory)
    finally:memory.close()


def restore_postgres(path,target):
    return import_rows(target,load_backup(path,target.cipher))


def activate_connection(source_file):
    """Only switch the default after a verified copy; never print credentials."""
    destination=default_database_file()
    raw=Path(source_file).read_bytes()
    if destination.exists():
        if destination.read_bytes()!=raw:
            raise StorageSecurityError('A different default database connection already exists; it was not replaced.')
    else:private_write(destination,raw)
    return destination
