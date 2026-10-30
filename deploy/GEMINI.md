# Gemini sample-data development

The backend supports Gemini generateContent structured JSON, retaining existing
quote validation, bounded retries and deterministic scoring. No keyword fallback.
Default model: `gemini-3.1-flash-lite`. Availability/quota depend on your Google project.
The app cannot determine whether your key has paid billing enabled; use a free-tier
project and check Google AI Studio quotas. No paid upgrade is performed by the app.

1. Create a key at https://aistudio.google.com/apikey . Do not paste it into chat,
   frontend settings, Git or command arguments.
2. In a local terminal run:

   ```powershell
   cd E:\CV-Shortlisted\backend
   .\.venv\Scripts\python.exe setup_gemini.py
   ```

3. Paste the key at the hidden prompt. The script creates an exclusive, private
   `%LOCALAPPDATA%\CVShortlisted\secrets\gemini.credentials.json` file using the
   existing current-user ACL helper. It never overwrites an existing file.
4. Restart the backend once to load the new adapter code. Subsequent configuration
   reads happen per request. Sign out/in to refresh the configuration banner.
5. Use the sample job/CVs or fictional pasted examples. Confirm the fake/sample-data
   checkbox, extract requirements, review criteria and match resumes.

Only synthetic data is authorized for this development adapter. Both AI endpoints
require explicit confirmation; this is a declaration, not automatic anonymization.
Do not open real saved applicant jobs in this mode. Parsed CV/JD text is sent to
Google, including source text needed for evidence. The database encryption does
not hide inputs from the AI provider. No external OCR/file upload, search tools,
provider file storage or explicit context cache is used.

`GEMINI_CONFIG_FILE` can point to another private secret file. Gemini is the only
AI provider; local models and the Ollama adapter have been removed. Old local-AI
environment variables are no longer used. Do not configure real candidate cloud processing by changing the
synthetic-only flag: this adapter intentionally refuses it.

Quota/auth/network errors are sanitized and do not trigger retry loops. Invalid
structured content gets at most one retry within the existing time budget. Results
record provider, requested model, returned model version when available, prompt,
policy and synthetic-only mode. Fixture tests do not establish real-model accuracy.

## Current evaluation contract (v3)

For all occupations the model selects criterion decisions and numbered CV line
ranges, never writes evidence quotations. The backend copies original text from
those ranges and excludes personal/contact fields. Relevant evidence still
requires semantic assessment; a valid source reference alone is not proof the
criterion is met. No occupation-specific scoring branches are used.

Unsupported/invalid references become needs-review with zero evidence credit for
that condition. They do not invalidate other criteria or produce an invented
quote. Parsed CVs with scored criteria receive a numeric evidence-coverage score;
if references fail validation the score is flagged provisional with a visible
warning. Zero credit means unverified evidence, not proven lack of qualification.
Unreadable/empty CVs remain unscored and must be re-uploaded or pasted as text.
Malformed schema, missing/duplicate criterion decisions or a provider outage
still fails explicitly instead of manufacturing a score. Historical saved results
remain unchanged and need re-matching for the new policy.

Official references:
- https://ai.google.dev/gemini-api/docs/generate-content/structured-output
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/api-key
