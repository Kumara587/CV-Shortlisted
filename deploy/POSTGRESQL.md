# PostgreSQL storage, local setup and migration

## Local deployment configured for this project

- PostgreSQL server: `127.0.0.1:5433`, bound only to loopback.
- Application database: `cv_shortlisted`; application role: `cv_app`.
- Dedicated test database: `cv_shortlisted_test` (never use production for tests).
- Server runtime: `E:\CVShortlistedRuntime\postgresql-18.6\pgsql\bin`.
- PostgreSQL cluster: `E:\CVShortlistedRuntime\data`, outside the Git project.
- Connection credentials: `%LOCALAPPDATA%\CVShortlisted\secrets\database.url`.
- Runtime/admin configuration: the same private directory's `local-postgres.json`.

Passwords are random, SCRAM authentication is enabled and credentials are not
printed or committed. The app role is not a server superuser. The bootstrap admin
credentials remain in a restricted file for local maintenance. The API reads the
private connection file automatically on this machine after verified cutover.
Production uses explicit `DATABASE_URL_FILE` or `DATABASE_URL`, with no SQLite
fallback. Invalid/missing configured credentials fail closed. Prefer the private
file to avoid exposing a password in shell history or environment listings.

From Windows CMD in `backend`:

```cmd
.venv\Scripts\python.exe manage.py start-postgres
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers --no-access-log --log-config ../deploy/logging.json
```

VS Code **Backend: start API** starts PostgreSQL as a dependency. This local server
is a user-owned background process, not a machine-wide Windows service. After a
reboot, start it using the command/task above. Stop it only after stopping the API:

```cmd
.venv\Scripts\python.exe manage.py stop-postgres
```

For another Windows machine, install trusted PostgreSQL binaries outside the repo
and run `setup_local_postgres.py --bin-dir <bin> --data-dir <new-empty-data-dir>
--port 5433`. This creates a separate cluster and refuses to replace a different
existing runtime configuration. Keep binary distributions outside source control.

## What is stored

`users` stores IDs, account names, token hashes and account status. `jobs` stores
encrypted titles, job descriptions, reviewed requirements and parsed CV text.
`screenings` stores encrypted historical inputs, evidence, scores, model/policy
versions, review decisions and export rows. `snapshots` stores temporary encrypted
exports. `storage_meta` checks that the correct encryption key is available.

CVs are currently retained as parsed text; original uploaded PDF/DOCX/TXT binary
files are still not retained. PostgreSQL migration does not change that product
behavior. Data is not sent to an LLM simply by moving it into PostgreSQL.

Sensitive columns remain Fernet ciphertext. Metadata, account names, IDs and
timestamps remain visible to database operators. Existing encryption keys and
their backups remain essential; the database password is not a replacement for
the encryption key. Owner filtering and API authentication continue to apply.

## Verified SQLite cutover

Stop all API writers and DB Browser transactions first. Keep the original key.
Use the target connection file created by local provisioning, not a new key.

```cmd
cd E:\CV-Shortlisted\backend
.venv\Scripts\python.exe manage.py migrate-postgres --source data\screener.sqlite3 --target-url-file "%LOCALAPPDATA%\CVShortlisted\secrets\postgres.target.url" --output data\backups\before-postgres.cvbackup --activate
.venv\Scripts\python.exe manage.py verify-encryption
```

Choose a new backup filename each time. Migration verifies source ciphertext,
makes an encrypted SQLite recovery backup, freezes source writes, copies accounts
and ciphertext without changing IDs or hashes, compares every row and verifies
decryption on the target before commit. A different non-empty target is refused.
An already identical copy can be verified again. The target transaction rolls back
on failure; original SQLite is never deleted. `--activate` writes the default
private connection file only after the copy is verified.

After cutover the old SQLite file is a frozen rollback source, not a live mirror.
Do not switch back casually after new PostgreSQL writes: those changes would not
exist in the old file. Restart the API and verify sign-in, opening the existing
job/CVs/history, review updates, exports and owner restrictions. Existing user
access tokens continue working because their hashes and IDs are preserved.

## Backups and recovery

The existing `backup-data` command now selects the active database backend:

```cmd
.venv\Scripts\python.exe manage.py backup-data --output D:\PrivateBackups\postgres.cvbackup
```

For PostgreSQL this is a consistent repeatable-read logical snapshot, encrypted
and verified before completion. It contains the application tables, not server
roles/configuration or other databases. It uses memory proportional to data size;
for larger deployments use a managed backup/WAL strategy as well. `pg_dump -Fc`
and `pg_restore` are alternatives for operator-managed PostgreSQL backups; protect
those archives because account metadata is not encrypted at the application level.

Restore into a separate empty application database using its private URL file:

```cmd
.venv\Scripts\python.exe manage.py restore-postgres --backup D:\PrivateBackups\postgres.cvbackup --target-url-file D:\PrivateBackups\empty-recovery-database.url
```

Recovery can import the new PostgreSQL backup format or an encrypted SQLite backup
whose protected columns were already migrated to field encryption. It refuses to
overwrite a different non-empty target. Do not pass a PostgreSQL backup to the old
SQLite `restore-data` command. Separately back up the encryption key using the
password-protected `backup-key` workflow in [ENCRYPTION.md](ENCRYPTION.md).

## Production Compose

Compose includes a private `postgres:18-alpine` service and persistent
`postgres_data` volume, with no published PostgreSQL port. Configure the existing
encryption-key secret plus these host secret files in `.env.production`:

- `POSTGRES_ADMIN_PASSWORD_FILE`: initialization admin password.
- `POSTGRES_APP_PASSWORD_FILE`: a different application-role password.
- `DATABASE_URL_FILE`: a private URL such as
  `postgresql://cv_app:<URL-ENCODED-APP-PASSWORD>@database:5432/cv_shortlisted`.

The initializer creates the non-superuser `cv_app` role and makes it owner of the
application database. Initializer scripts only run for a new empty data volume;
changing a password file later does not change an existing PostgreSQL password.
Provision secret permissions for each actual container UID. The API connection
file must be readable only by its UID 10001; database initialization secrets must
be readable by the PostgreSQL container process. Protect host parent directories
and verify bind-backed Compose secret permissions on the deployment host.

PostgreSQL 18 mounts data at `/var/lib/postgresql`. Keep this volume across updates.
Do not remove the SQLite/backup volume during initial migration. For externally
managed PostgreSQL, use provider-required TLS certificate validation, a private
network and appropriate database roles. Docker deployment is not validated on this
Windows machine because Docker is unavailable; local native PostgreSQL is tested.

Shared repository writes currently use a transaction-scoped advisory lock to
preserve quota checks and concurrent JSON review updates. This conservative
serialization favors consistency; measure throughput and introduce finer-grained
locking/pooling before scaling to many API instances. Statement/lock timeouts are
bounded and database exceptions do not echo credentials or sensitive payloads.

## Tests

Run from `backend` in PowerShell, using only the dedicated test connection file:

```powershell
$env:PG_TEST_URL_FILE = "$env:LOCALAPPDATA\CVShortlisted\secrets\postgres.test.url"
.\.venv\Scripts\python.exe -m pytest -q
```

PostgreSQL tests create uniquely named schemas in the `*_test` database and drop
only those schemas afterward. They verify migration, ciphertext equality, account
continuity, ownership, history, export/review updates, backup/restore and concurrent
reviews. Without this variable, PostgreSQL integration tests skip explicitly.

References: [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html),
[PostgreSQL backups](https://www.postgresql.org/docs/current/app-pgdump.html),
[official PostgreSQL image](https://hub.docker.com/_/postgres).
