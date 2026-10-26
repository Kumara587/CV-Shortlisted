import json
import sqlite3
import os
from pathlib import Path
import pytest
from cryptography.fernet import Fernet
from encryption import (Cipher, StorageSecurityError, MigrationRequired, PREFIX,
                        CHECK_CONTEXT, initialize_key)
from storage_admin import migrate, backup, restore, read_backup
from store import Store
from test_library import workspace


def populated(tmp_path):
    store=Store(tmp_path/'screener.sqlite3')
    owner,token=store.create_user('tester')
    w=workspace('PrivateJobMarker913');w['candidates'][0]['text']='PrivateCVMarker582 Python'
    job=store.save_job(owner,w)
    result={'results':[{'id':'a','rank':1,'score':100,'group':'requirements_review',
        'review_status':'pending','skills':[{'name':'Python','status':'supported'}],
        'missing_or_uncertain':[],'must_have_issues':[]}],'notice':'PrivateEvidenceMarker427'}
    run=store.save_run(owner,job['id'],w['requirements'],w['candidates'],result)
    snapshot,_=store.save(owner,result['results'],{'a':'PrivateLabelMarker294'})
    return store,owner,token,job['id'],run,snapshot


def test_all_sensitive_columns_encrypted_and_reopen(tmp_path):
    store,owner,token,job,run,snapshot=populated(tmp_path)
    raw=store.path.read_bytes()
    for marker in [b'PrivateJobMarker913',b'PrivateCVMarker582',b'PrivateEvidenceMarker427',b'PrivateLabelMarker294']:
        assert marker not in raw
    reopened=Store(store.path)
    assert reopened.authenticate(token)==owner
    assert reopened.job(owner,job)['workspace']['title']=='PrivateJobMarker913'
    assert reopened.run(owner,run)['result']['notice']=='PrivateEvidenceMarker427'
    reopened.review(owner,run,'a','shortlisted')
    reopened.review(owner,snapshot,'a','reviewed')
    assert reopened.get(owner,run)[0][0]['review_status']=='shortlisted'
    assert reopened.get(owner,snapshot)[0][0]['review_status']=='reviewed'


def test_wrong_missing_key_and_no_plaintext_fallback(tmp_path,monkeypatch):
    store,owner,_,job,_,_=populated(tmp_path)
    before=store.path.read_bytes()
    wrong=Store(store.path,cipher=Cipher([Fernet.generate_key()]))
    with pytest.raises(StorageSecurityError): wrong.job(owner,job)
    monkeypatch.setenv('SCREENER_KEY_FILE',str(tmp_path/'missing.key'))
    with pytest.raises(StorageSecurityError): Store(store.path).list_jobs(owner)
    assert not (tmp_path/'missing.key').exists()
    assert store.path.read_bytes()==before


def test_tamper_and_cross_record_swaps_rejected(tmp_path):
    store,owner,_,job,_,_=populated(tmp_path)
    other=store.save_job(owner,workspace('Other'))['id']
    with store.connection() as db:
        value=db.execute('SELECT workspace FROM jobs WHERE id=?',(job,)).fetchone()[0]
        db.execute('UPDATE jobs SET workspace=? WHERE id=?',(value,other))
    with pytest.raises(StorageSecurityError): store.job(owner,other)
    with store.connection() as db:
        db.execute('UPDATE jobs SET title=? WHERE id=?',(PREFIX+'bad',job))
    with pytest.raises(StorageSecurityError): store.list_jobs(owner)


def legacy(store):
    """Synthetic old schema rows; never use a real CV fixture."""
    owner,token=store.create_user('legacy')
    w=workspace('LegacyPrivateTitle642')
    w['candidates'][0]['text']='LegacyPrivateCV753 Python'
    with store.connection() as db:
        db.execute('DELETE FROM storage_meta')
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',('job_old',owner,w['title'],json.dumps(w),1,1))
        db.execute('INSERT INTO snapshots VALUES(?,?,?,?)',('old',owner,9999999999,json.dumps([{'id':'a','review_status':'pending'}])))
    return owner,token,w


def test_legacy_migration_encrypted_backup_and_recovery(tmp_path):
    store=Store(tmp_path/'legacy.sqlite3')
    owner,token,w=legacy(store)
    with pytest.raises(MigrationRequired): store.job(owner,'job_old')
    destination=tmp_path/'before.cvbackup'
    assert migrate(store,destination)==2
    assert store.job(owner,'job_old')['workspace']==w
    assert store.authenticate(token)==owner
    assert b'LegacyPrivateCV753' not in store.path.read_bytes()
    assert b'LegacyPrivateTitle642' not in store.path.read_bytes()
    assert b'LegacyPrivateCV753' not in destination.read_bytes()
    recovered=tmp_path/'recovered.sqlite3'
    restore(destination,recovered,store.cipher)
    assert Store(recovered).job(owner,'job_old')['workspace']==w
    assert b'LegacyPrivateCV753' not in recovered.read_bytes()


def test_backup_restore_key_loss_tamper_and_never_overwrite(tmp_path):
    store,owner,_,job,run,_=populated(tmp_path)
    destination=tmp_path/'backup.cvbackup'
    backup(store,destination)
    with pytest.raises(FileExistsError): backup(store,destination)
    restored=tmp_path/'restored.sqlite3'
    restore(destination,restored,store.cipher)
    assert Store(restored).run(owner,run)['job_id']==job
    before=restored.read_bytes()
    with pytest.raises(StorageSecurityError): restore(destination,restored,store.cipher)
    assert restored.read_bytes()==before
    with pytest.raises(StorageSecurityError): read_backup(destination,Cipher([Fernet.generate_key()]))
    damaged=bytearray(destination.read_bytes());damaged[-20]^=1
    destination.write_bytes(damaged)
    with pytest.raises(StorageSecurityError): read_backup(destination,store.cipher)


def test_migration_failure_rolls_back_every_record(tmp_path,monkeypatch):
    store=Store(tmp_path/'legacy.sqlite3')
    owner,_,w=legacy(store)
    original=store.cipher.seal
    def fail(value,context):
        if context[0]=='snapshots': raise StorageSecurityError('Synthetic failure')
        return original(value,context)
    monkeypatch.setattr(store.cipher,'seal',fail)
    with pytest.raises(StorageSecurityError): migrate(store,tmp_path/'recovery.cvbackup')
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT title FROM jobs').fetchone()[0]==w['title']
        assert db.execute('SELECT count(*) FROM storage_meta').fetchone()[0]==0
    assert (tmp_path/'recovery.cvbackup').is_file()


def test_key_file_never_overwritten(tmp_path):
    path=tmp_path/'new.keys.json'
    initialize_key(path)
    before=path.read_bytes()
    with pytest.raises(FileExistsError): initialize_key(path)
    assert path.read_bytes()==before


def test_keyring_rotation_and_old_backup_recovery(tmp_path):
    store,owner,_,job,_,_=populated(tmp_path)
    old_keys=json.loads(Path(os.environ['SCREENER_KEY_FILE']).read_text())['keys']
    new_key=Fernet.generate_key()
    rotated=Store(store.path,cipher=Cipher([new_key,*old_keys]))
    migrate(rotated,tmp_path/'old-key-backup.cvbackup')
    assert Store(store.path,cipher=Cipher([new_key])).job(owner,job)['workspace']['title']=='PrivateJobMarker913'
    with pytest.raises(StorageSecurityError): Store(store.path,cipher=Cipher(old_keys)).job(owner,job)


def test_password_protected_key_backup_and_recovery(tmp_path):
    from encryption import backup_key,restore_key
    source=Path(os.environ['SCREENER_KEY_FILE'])
    destination=tmp_path/'key.keybackup'
    password='synthetic recovery password 123!'
    backup_key(destination,password)
    assert source.read_bytes() not in destination.read_bytes()
    restored=tmp_path/'restored.keys.json'
    with pytest.raises(StorageSecurityError): restore_key(destination,restored,'wrong password')
    assert not restored.exists()
    restore_key(destination,restored,password)
    assert restored.read_bytes()==source.read_bytes()
    with pytest.raises(FileExistsError): restore_key(destination,restored,password)
