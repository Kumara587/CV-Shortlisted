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
no hosted AI API or API key is used. Requirements extraction is still rule-based.

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
