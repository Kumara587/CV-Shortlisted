# Hosted AI evaluation

Gemini is the only AI provider used by the application. Local Ollama and Sentence
Transformers integrations, setup scripts, model weights and optional dependencies
have been removed. No local general-purpose LLM runtime is needed.

See [Gemini setup](GEMINI.md) for private API-key configuration, sample-data
confirmation, structured-output constraints and versioned evidence scoring.

The current UI calls `/api/ai/requirements/extract` and
`/api/ai/shortlist/match`. The model extracts occupation-independent criteria and
selects CV source line references. The backend copies original source text,
validates references and computes weighted evidence coverage. It never uses a
model-invented numeric score or silently substitutes keyword matching.

Required criteria have weight 3, preferred 1, review-only 0. Meets earns full
credit, partially meets half, and missing/uncertain evidence zero. Invalid source
references produce needs-review conditions and provisional numeric coverage,
not a conclusion that a qualification is absent. Unreadable CVs remain unscored.
Every result requires human review; these rules are not HR-calibrated accuracy.

Requests have bounded input/response sizes, timeouts and at most one validation
retry. Provider/auth/quota failures are surfaced directly without fallback.
Provider, model, prompt and scoring-policy versions remain in encrypted history.

Old explicit extraction/matching endpoints remain for API compatibility and
historical results; they do not load local ML packages. Old saved semantic
results can still be viewed as historical records without their original model.

CV parsing, encrypted PostgreSQL storage, accounts and saved screening history
remain unchanged by removing local AI. PDF parsing may retain NumPy/ONNX-related
packages required by the installed PyMuPDF version; these are independent of the
removed Sentence Transformers/PyTorch matching stack.