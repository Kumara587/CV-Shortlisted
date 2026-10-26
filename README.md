# CV-Shortlisted

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

## Local AI semantic matching

The matching endpoint now combines explicit skill evidence with local Sentence
Transformers embeddings (`all-MiniLM-L6-v2`). Candidate text is processed locally;
no hosted AI API or API key is used. Job-description extraction preserves source clauses and uses local AI for clause classification when the model is available; see the extraction section below.

Install and download the model once from the project root:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe setup_semantic.py
```

Restart the backend after setup. Model files stay in `backend/models/` (gitignored).
`SEMANTIC_MODEL_PATH` can point to another local Sentence Transformers model folder.
Runtime loads local files only; model downloads happen only during setup.

Explicit skills earn full credit. Previously unevidenced skills with cosine
similarity >= 0.60 receive `semantic_review` status and half credit, with original
source-line evidence. This threshold is an initial heuristic, not a validated
hiring metric or probability. Negated, uncertain and labeled demographic lines
are excluded from semantic evidence. Semantic matches never clear must-have
verification flags. Experience and education continue using explicit evidence.
The UI shows semantic evidence and similarity; CSV retains these skills under
missing/uncertain until human review. Human review does not change evidence scores.

Inference examines at most 256 text windows per CV. Longer resumes may have
unexamined semantic evidence. The supplied model targets English; Sinhala/Tamil
and domain-specific accuracy require separate evaluation. If loading or inference
fails, matching falls back to explicit evidence with a visible warning.

Run tests with `.\.venv\Scripts\python.exe -m pytest -q` from `backend`.
Docker deployments must install `requirements-semantic.txt` and provision the
model as well; the existing lightweight container uses explicit matching otherwise.

Library reference: https://www.sbert.net/docs/package_reference/sentence_transformer/model.html

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

Storage uses the existing SQLite file (`backend/data/screener.sqlite3`, or
`SCREENER_DATA_DIR`). New `jobs` and `screenings` tables are added automatically
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


## Job-description requirements extraction

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
