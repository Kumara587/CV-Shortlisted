"""Authenticated, context-bound field encryption. Keys never live in SQLite."""
import json
import os
from pathlib import Path
import stat
import subprocess

from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

PREFIX = 'enc:v1:'


class StorageSecurityError(Exception):
    """Safe diagnostic; never includes keys, tokens or candidate content."""


class MigrationRequired(StorageSecurityError):
    pass


def key_path():
    configured = os.getenv('SCREENER_KEY_FILE')
    if configured:
        return Path(configured).expanduser()
    if os.getenv('APP_ENV') == 'production':
        raise StorageSecurityError('Production requires SCREENER_KEY_FILE pointing to a separate mounted secret.')
    base = Path(os.getenv('LOCALAPPDATA', str(Path.home()/'.config')))
    return base/'CVShortlisted'/'secrets'/'storage.keys.json'


def private_write(path, data):
    """Create only; never overwrite an existing key, database or recovery file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        if os.name == 'nt':
            identity = subprocess.check_output(['whoami'], text=True).strip()
            subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', identity+':(F)'],
                           check=True, capture_output=True)
        with os.fdopen(fd, 'wb') as stream:
            fd = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if fd is not None: os.close(fd)
        path.unlink(missing_ok=True)
        raise


def initialize_key(path=None):
    path = Path(path) if path else key_path()
    private_write(path, json.dumps({'version':1, 'keys':[Fernet.generate_key().decode('ascii')]}).encode())
    return path


class Cipher:
    def __init__(self, keys):
        try:
            if not isinstance(keys,list) or not keys or len(keys)>10: raise ValueError()
            self.fernet = MultiFernet([Fernet(k) for k in keys])
        except (ValueError, TypeError):
            raise StorageSecurityError('Invalid encryption key configuration.') from None

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path else key_path()
        try:
            if os.name != 'nt' and stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise StorageSecurityError('Encryption key file must be private (chmod 600).')
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or data.get('version') != 1: raise ValueError()
            return cls(data['keys'])
        except (OSError, ValueError, KeyError, TypeError):
            raise StorageSecurityError('Encryption key is missing or invalid. Restore the existing key; never replace it with a new key for encrypted data.') from None

    def encrypt_bytes(self, data):
        return self.fernet.encrypt(data)

    def decrypt_bytes(self, data):
        try: return self.fernet.decrypt(data)
        except (InvalidToken, TypeError):
            raise StorageSecurityError('Encrypted data cannot be verified. Check the key or restore a verified backup.') from None

    def seal(self, value, context):
        message=json.dumps({'context':list(context),'value':value},ensure_ascii=True).encode('utf-8')
        return PREFIX+self.encrypt_bytes(message).decode('ascii')

    def open(self, value, context):
        if not isinstance(value,str) or not value.startswith(PREFIX):
            raise MigrationRequired('Unencrypted data detected. Stop the backend and run migrate-encryption.')
        try:
            message=json.loads(self.decrypt_bytes(value[len(PREFIX):].encode('ascii')))
            if message['context']!=list(context) or not isinstance(message['value'],str): raise ValueError()
            return message['value']
        except (ValueError,KeyError,UnicodeError,TypeError):
            raise StorageSecurityError('Encrypted data context cannot be verified.') from None


FIELDS = {'jobs':('title','workspace'), 'screenings':('document','export_rows'), 'snapshots':('payload',)}
CHECK_CONTEXT = ('storage_meta','check','','1')
KEY_BACKUP_MAGIC=b'CVKEYBACKUP1\n'


def backup_key(destination,password,path=None):
    if len(password)<16:
        raise StorageSecurityError('Use a recovery passphrase of at least 16 characters.')
    path=Path(path) if path else key_path()
    Cipher.load(path)
    salt=os.urandom(16); nonce=os.urandom(12)
    key=Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode('utf-8'))
    data=AESGCM(key).encrypt(nonce,path.read_bytes(),KEY_BACKUP_MAGIC+salt)
    private_write(destination,KEY_BACKUP_MAGIC+salt+nonce+data)


def restore_key(source,destination,password):
    data=Path(source).read_bytes()
    if not data.startswith(KEY_BACKUP_MAGIC) or len(data)>65536 or len(data)<len(KEY_BACKUP_MAGIC)+44:
        raise StorageSecurityError('Invalid encrypted key backup.')
    offset=len(KEY_BACKUP_MAGIC)
    salt=data[offset:offset+16];nonce=data[offset+16:offset+28]
    key=Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode('utf-8'))
    try:
        raw=AESGCM(key).decrypt(nonce,data[offset+28:],KEY_BACKUP_MAGIC+salt)
        parsed=json.loads(raw)
        if parsed.get('version')!=1: raise ValueError()
        Cipher(parsed['keys'])
    except (InvalidTag,ValueError,KeyError,TypeError,AttributeError):
        raise StorageSecurityError('Wrong recovery passphrase or damaged key backup.') from None
    private_write(destination,raw)


def verify_or_initialize(db, cipher, maintenance=False):
    db.execute('CREATE TABLE IF NOT EXISTS storage_meta(id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL)')
    row=db.execute('SELECT token FROM storage_meta WHERE id=1').fetchone()
    if row:
        if cipher.open(row[0],CHECK_CONTEXT)!='cv-storage-v1':
            raise StorageSecurityError('Encryption key check failed.')
    elif not maintenance:
        if any(db.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone() for table in FIELDS):
            raise MigrationRequired('Existing records require migrate-encryption before the backend can start.')
        db.execute('INSERT INTO storage_meta VALUES(1,?)',(cipher.seal('cv-storage-v1',CHECK_CONTEXT),))


def encrypt_existing(db,cipher):
    """Caller owns one transaction. Validate encrypted fields; migrate plaintext."""
    count=0
    for table,columns in FIELDS.items():
        for row in db.execute(f"SELECT id,owner,{','.join(columns)} FROM {table}").fetchall():
            updates=[]
            for column,value in zip(columns,row[2:]):
                context=(table,column,row[1],row[0])
                if value.startswith(PREFIX):
                    value=cipher.open(value,context)
                updates.append(cipher.seal(value,context))
            db.execute(f"UPDATE {table} SET {','.join(c+'=?' for c in columns)} WHERE id=?",(*updates,row[0]))
            count+=1
    db.execute('INSERT OR REPLACE INTO storage_meta VALUES(1,?)',(cipher.seal('cv-storage-v1',CHECK_CONTEXT),))
    return count


def verify_fields(db,cipher):
    count=0
    verify_or_initialize(db,cipher,maintenance=True)
    for table,columns in FIELDS.items():
        for row in db.execute(f"SELECT id,owner,{','.join(columns)} FROM {table}"):
            for column,value in zip(columns,row[2:]):
                cipher.open(value,(table,column,row[1],row[0]))
            count+=1
    return count
