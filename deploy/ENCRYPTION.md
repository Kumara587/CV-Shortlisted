# CV storage encryption and recovery

## What is protected

`jobs.title`, `jobs.workspace`, `screenings.document`, `screenings.export_rows`
and `snapshots.payload` are authenticated ciphertext, including CV text, job
descriptions, evidence, scores, review decisions and candidate labels. Each field
is bound to its table, column, owner and record ID, so swapping ciphertext into
another owner's row is rejected. Fernet uses randomized authenticated encryption
from the cryptography library; no custom encryption primitive is implemented.

Account names, token hashes, IDs, timestamps, relationships, row counts and sizes
are metadata and remain visible. This does not prevent an authorized user, a
compromised app/server account, or someone holding both the database and key from
reading data. Keep server disks encrypted too. Downloaded CSVs and original CVs
on users' devices are separate plaintext copies. Old OS snapshots, backups and
SSD remnants are not retroactively erased by migration or VACUUM.

## Key location and permissions

The Windows default is `%LOCALAPPDATA%\CVShortlisted\secrets\storage.keys.json`.
It is outside the repository and database directory. `SCREENER_KEY_FILE` can point
to another private file. Production requires this variable and does not generate
keys. New key/recovery files are exclusive-create only, mode 0600 on POSIX and
an inheritance-disabled current-user ACL on Windows. No command prints the key.
Filenames ending `.keys.json`, `.keybackup` or `.cvbackup` are excluded from Git
and the Docker build context. These exclusions do not secure arbitrary file names.

Do not regenerate a key when the app reports that its key is missing. Restore
the original key. Deleting this file without a recovery copy loses data access.

## First installation or upgrading plaintext records (Windows CMD)

Stop the backend and close DB Browser before maintenance. All app instances must
use the new code; an old backend can still write plaintext into the database.

```cmd
cd E:\CV-Shortlisted\backend
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Only if the key file does not already exist:

```cmd
.venv\Scripts\python.exe manage.py init-encryption
```

For an existing database, choose a fresh backup filename:

```cmd
.venv\Scripts\python.exe manage.py migrate-encryption --output data\backups\before-encryption.cvbackup
.venv\Scripts\python.exe manage.py verify-encryption
```

The tool makes and verifies an encrypted SQLite recovery backup before migrating.
Encryption updates run in one exclusive transaction. Wrong keys or a failure
before commit leave the original records unchanged. After commit it rebuilds the
database to remove free pages and verifies every protected field. If post-commit
verification/VACUUM fails, the verified backup remains for recovery; investigate
before restarting. No plaintext backup file is created. Migration and backups use
memory proportional to database size, so provision enough RAM and disk space.

Restart the backend after verification. Existing accounts, tokens, job IDs and
screening IDs are preserved. The app decrypts records only after owner checks.

## Back up the key separately

Choose a path on separate protected storage, not the database disk:

```cmd
.venv\Scripts\python.exe manage.py backup-key --output D:\PrivateBackups\cv-storage.keybackup
```

Enter a strong unique recovery passphrase of at least 16 characters twice at the
hidden prompts. The key backup uses Scrypt (N=32768,r=8,p=1) and AES-256-GCM with a
random salt/nonce. Keep the passphrase separately in your password manager. The
app cannot choose this private passphrase for you. Test restoration before
relying on your recovery copy, and keep old keys required by historical backups.

## Back up data and test recovery

```cmd
.venv\Scripts\python.exe manage.py backup-data --output D:\PrivateBackups\cv-data.cvbackup
.venv\Scripts\python.exe manage.py restore-data --backup D:\PrivateBackups\cv-data.cvbackup --output data\recovery-test.sqlite3
```

`restore-data` never overwrites an existing file. It authenticates the entire
backup, checks SQLite integrity, and encrypts sensitive fields in memory before
creating the recovery database. Keep data backups separate from the live key.
Successful restore is not a disaster-recovery plan until you have tested logging
in and reopening jobs using the recovered database and recovered key.

On a replacement machine, restore the key first:

```cmd
.venv\Scripts\python.exe manage.py restore-key --backup D:\PrivateBackups\cv-storage.keybackup
```

It prompts for the recovery passphrase and refuses to overwrite any current key.
Use `--output` for a separate test key file. To verify a test recovery without
changing the live app, use a NEW CMD window:

```cmd
set SCREENER_KEY_FILE=D:\PrivateBackups\recovered.keys.json
set SCREENER_DATA_DIR=E:\CV-Recovery-Test
.venv\Scripts\python.exe manage.py verify-encryption
```

Place the recovered database at that separate directory's `screener.sqlite3`
before verifying. An empty new database verifies zero records, which is not proof
that your backup was restored. Do not change or delete the live database until
the recovered data and account access have been checked.

## Planned key rotation

The key file is a versioned JSON keyring; new writes use its first key. Offline,
provision a new random Fernet key first while retaining old keys in the keyring,
make a recovery backup, and run `migrate-encryption` to re-encrypt every protected
field and the key-check marker. Verify using only the new key on a separate copy
before retiring old keys from the live keyring. Retain protected copies of keys
needed by old recovery backups. Existing key files are never overwritten by the
initializer or recovery command. Coordinate rotation across all processes.

Reference: https://cryptography.io/en/stable/fernet/
