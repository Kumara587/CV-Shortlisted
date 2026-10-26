"""Offline encrypted backup/migration/recovery. No plaintext backup files."""
from pathlib import Path
import sqlite3
from encryption import (StorageSecurityError, private_write, encrypt_existing,
                        verify_fields, verify_or_initialize)

MAGIC=b'CVBACKUP1\n'
INNER=b'cv-sqlite-backup-v1\x00'


def backup_connection(db,cipher,destination):
    memory=sqlite3.connect(':memory:')
    try:
        db.backup(memory)
        if memory.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise StorageSecurityError('Database integrity check failed; migration stopped.')
        data=memory.serialize()
        encrypted=MAGIC+cipher.encrypt_bytes(INNER+data)
        if cipher.decrypt_bytes(encrypted[len(MAGIC):])!=INNER+data:
            raise StorageSecurityError('Encrypted backup verification failed.')
        private_write(destination,encrypted)
        # Verify the actual on-disk copy before changing the source database.
        restored=read_backup(destination,cipher)
        restored.close()
    finally:
        memory.close()


def read_backup(source,cipher):
    data=Path(source).read_bytes()
    if not data.startswith(MAGIC): raise StorageSecurityError('Not an encrypted CV backup.')
    data=cipher.decrypt_bytes(data[len(MAGIC):])
    if not data.startswith(INNER+b'SQLite format 3\x00'):
        raise StorageSecurityError('Backup content cannot be verified.')
    memory=sqlite3.connect(':memory:')
    try:
        memory.deserialize(data[len(INNER):])
        if memory.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise StorageSecurityError('Backup integrity check failed.')
        return memory
    except BaseException:
        memory.close()
        raise


def migrate(store,backup_path):
    with store.connection(maintenance=True) as db:
        version=db.execute('PRAGMA data_version').fetchone()[0]
        backup_connection(db,store.cipher,backup_path)
        db.execute('BEGIN EXCLUSIVE')
        if db.execute('PRAGMA data_version').fetchone()[0]!=version:
            raise StorageSecurityError('Database changed during backup. Stop all backend writers and retry.')
        count=encrypt_existing(db,store.cipher)
        verify_fields(db,store.cipher)
        db.commit()
        # Rebuild free pages after committing the encrypted records.
        db.execute('VACUUM')
        verify_fields(db,store.cipher)
        return count


def backup(store,destination):
    with store.connection() as db:
        verify_fields(db,store.cipher)
        backup_connection(db,store.cipher,destination)


def restore(source,destination,cipher):
    destination=Path(destination)
    if destination.exists():
        raise StorageSecurityError('Restore destination must be a new file; existing databases are never overwritten.')
    memory=read_backup(source,cipher)
    try:
        memory.execute('PRAGMA secure_delete=ON')
        verify_or_initialize(memory,cipher,maintenance=True)
        memory.commit()
        memory.execute('BEGIN')
        encrypt_existing(memory,cipher)
        verify_fields(memory,cipher)
        memory.commit()
        memory.execute('VACUUM')
        # Even pre-migration recovery backups are encrypted before writing to disk.
        private_write(destination,memory.serialize())
    finally:
        memory.close()
