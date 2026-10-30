# CV-Shortlisted

The frontend now uses email/password accounts and HttpOnly cookie sessions.
See [authentication setup](deploy/AUTH.md) for Google sign-in, SMTP password
recovery, and attaching email login to an existing recruiter's saved workspace.
Google OAuth/SMTP require your own configuration; local email signup/login work
without them. No access token is entered or stored by the frontend.

PostgreSQL is now the configured local database. See [PostgreSQL setup, migration and recovery](deploy/POSTGRESQL.md). Users, encrypted parsed CV text, jobs, screening history, reviews and exports use the same storage service. SQLite is retained only for migration/compatibility and the untouched rollback source.

The current UI uses the LLM extraction/evaluation service described in
[LLM setup and validation](deploy/LLM.md) and [Gemini sample-data setup](deploy/GEMINI.md). Without a configured AI provider it shows
**AI evaluation unavailable** and creates no substitute keyword score. Existing
parsing, encrypted storage and saved history remain available. The earlier
keyword/embedding endpoints are legacy APIs for compatibility and old history.

## VS Code PowerShell activation error

The workspace selects `backend/.venv/Scripts/python.exe` directly and disables
Python terminal auto-activation. Reload VS Code and create a new terminal after
changing these settings. No execution-policy change or `Activate.ps1` is needed.

Use **Terminal > Run Task > Backend: start API**, or run from the project root:

```powershell
cd E:\CV-Shortlisted\backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers --no-access-log --log-config ../deploy/logging.json
```

For tests, use `.\.venv\Scripts\python.exe -m pytest -q` from `backend`.
An existing terminal may still show an earlier activation error; open a fresh one.

## Backend setup on Windows (PowerShell)

From the project root, use the installed `python` command. The optional `py`
launcher is not required. Run each step only after the previous step succeeds.

```powershell
cd backend
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Once for a NEW installation only; never replace an existing encryption key:
.\.venv\Scripts\python.exe manage.py init-encryption
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe manage.py create-user recruiter
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers --no-access-log --log-config ../deploy/logging.json
```

Save the access token printed by `create-user`; it is shown only once.
If `python` is also unavailable, install Python 3.11 and enable **Add Python to
PATH**, then open a new PowerShell window before retrying.

## Hosted AI

Gemini is the only current AI provider. No Ollama runtime, Sentence Transformers,
PyTorch or downloaded embedding model is required. See [Gemini configuration](deploy/GEMINI.md).
Legacy explicit matching remains available only for compatibility, without local AI.

## Saved jobs, CV text and screening history

1. Enter a job title, job description and requirements, then add CVs.
2. Select **Save job & CVs**. This explicitly saves the full parsed CV text,
   labels and requirements to your account. Original PDF/DOCX/TXT bytes are not
   retained; saved text can be reopened and matched without uploading again.
3. Review requirements and select **Match resumes**. For a saved job, each match
   creates a permanent screening run containing that version of the job inputs,
   candidates, matching method, scores, source evidence and review decisions.
4. Use **Open job** to restore the latest saved inputs, or **Open screening** to
   restore historical inputs and results. Saved runs support reviews and CSV
   downloads after a restart or sign-in on another browser.
5. **Update saved job & CVs** updates current inputs without rewriting old runs.
   **New job** starts a separate workspace. Unsaved edits are not auto-saved.

Storage uses the configured PostgreSQL database. `backend/data/screener.sqlite3`
is the retained pre-migration source; it no longer receives live app changes after cutover. New `jobs` and `screenings` tables are added automatically
without removing existing users or temporary snapshots. No database recreation,
new packages or account recreation is required. Restart the backend and reload
frontend after upgrading.

Saved jobs and runs do not expire. The temporary `RETENTION_SECONDS` setting only
applies to unsaved export snapshots. Clearing the current workspace, sign-out,
revoking a token, or deleting temporary exports does not delete persistent jobs.
Use the explicit deletion controls: deleting a job also deletes its CV text and
all screening runs; deleting one screening leaves the saved job intact. Updating
or removing a CV from a job does not remove its historical copies in old runs.
Each account is limited to 100 jobs, 100 runs per job, and 100 MiB of serialized
library data. Other accounts cannot list, open, change, export or delete these
records. Sensitive database fields are encrypted by the app; protect the separate key
file and encrypted backups. See the encryption and recovery guide below. App deletion does not delete downloaded CSVs or backups.

Authenticated endpoints: `GET/POST /api/jobs`, `GET/PATCH/DELETE /api/jobs/{id}`,
`GET /api/jobs/{id}/runs`, and `GET/DELETE /api/screenings/{id}`. A matching request
can supply `job_id` to persist the result. Existing shortlist review and export
endpoints accept the returned durable `run_...` ID.


## Encrypted storage and recovery

See [the complete encryption guide](deploy/ENCRYPTION.md) before changing keys.
Sensitive fields (job titles/descriptions, CV text, evidence, scores, review data
and temporary exports) use authenticated Fernet encryption. Keys are separate
from SQLite and are never printed. Missing/wrong keys and altered ciphertext
fail closed. This is field encryption, not whole-file SQLite encryption: account
names, opaque IDs, timestamps, relationships and record sizes remain visible.
DB Browser will show encrypted text in the protected columns; normal app access
still shows decrypted data after authentication.

On Windows the default key location is
`%LOCALAPPDATA%\CVShortlisted\secrets\storage.keys.json`, outside this repository.
`SCREENER_KEY_FILE` overrides it; production requires an explicit mounted secret.
Existing plaintext records require an offline migration with an encrypted recovery
backup. The key file must survive reinstalls and deployments. Losing the key and
its recovery backup means losing access to saved CVs.

A password-protected, portable key backup can be created interactively:

```cmd
cd E:\CV-Shortlisted\backend
.venv\Scripts\python.exe manage.py backup-key --output D:\PrivateBackups\cv-storage.keybackup
```

Choose a long recovery passphrase at the hidden prompts. Store the `.keybackup`
on separate protected storage and the passphrase in a password manager. Do not
paste keys or recovery passwords into chat, source code or shell arguments.


## Legacy source-based requirements extraction

The extractor no longer relies only on a fixed technology keyword list. It keeps
source clauses for skills, qualifications, experience, language proficiency and
duties across job fields. Recognized tools retain canonical names; unfamiliar
skills under skills headings are also surfaced. The existing local embedding
model assists classification of clauses without a recognized section. It does
not generate new requirements or call a hosted AI service.

Each clause includes its original source text/line and a required, preferred or
needs-review label. Preferred degrees are not converted into required minimum
degrees. School examination conditions, subjects/grades, professional
qualifications and degree alternatives remain visible for manual verification.
The UI lets users edit/remove clauses and labels, and remove irrelevant skill
chips. These details survive saving a job and reopening screening history.

Additional clauses are explicitly manual-review items and do not contribute to
the existing skills/years/degree score. Requiring a school credit or professional
certification does not mean the current matcher automatically verifies it.
The full HR Assistant regression example covers A/L, O/L subject credits/two
sittings, preferred HRM qualifications, one year of HR experience, confidentiality,
communication/languages, interpersonal skills, teamwork, pressure and timeliness.
Other tests cover chef, nursing, accounting and technical skills.

Source extraction is bounded to 100 clauses/100 skill chips, 1,000 characters per
clause and the existing 20,000-character JD limit. Warnings identify truncation,
local-model unavailability and omitted protected criteria. Long/complex prose,
negations and alternatives still need review; arbitrary job descriptions cannot
be promised 100% extraction accuracy. No new model download or API key is needed.
Restart the backend and refresh the browser to load this version.
