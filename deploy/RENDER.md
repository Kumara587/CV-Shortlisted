# Render Free pilot with Neon

The Render release uses `Dockerfile.render`, not the VPS Compose stack. It builds
React assets and serves them with Caddy on `$PORT`, forwarding `/api/*` and
`/health` to FastAPI on loopback only. Render terminates public TLS; the local
proxy supplies the HTTPS scheme and uvicorn trusts only 127.0.0.1. The frontend
and API share one HTTPS origin, preserving HttpOnly session cookies and CSRF
checks. No database credential is exposed to React.

## Runtime configuration

Render supplies `RENDER_EXTERNAL_HOSTNAME` and `PORT`. The startup script derives
the allowed hostname/origin from that hostname, or respects explicitly supplied
`ALLOWED_HOSTS`/`CORS_ORIGINS` for a future custom domain.

Required private Render environment values:

- `DATABASE_URL`: verified Neon database connection. The existing external
  encryption key must match migrated records. The current persistent worker uses
  a direct connection because its connection-scoped timeout options were verified
  on direct Neon connections; pooled connection compatibility remains separate.
- `SCREENER_STORAGE_KEY_JSON`: contents of the existing external key JSON.
- `SCREENER_GEMINI_JSON`: contents of the private Gemini configuration JSON.
- `SCREENER_AUTH_JSON`: private auth config JSON, or `{}` until OAuth/email setup.

`render_start.py` writes restricted temporary runtime files from these values,
removes the JSON variables from child-process environments, and sets the existing
file-based configuration variables. Secrets are never printed, committed or
copied into the Docker build. They must persist in Render configuration across
restarts; do not generate a new encryption key on restart.

Defaults are one parser, one password-hashing operation and one model evaluation
at a time. Periodic database cleanup is disabled so Neon can suspend; expiry is
still checked on reads and on new sessions. Startup performs expired-row cleanup.
The app runs one API worker with the existing process-local request limiter.

## Current limitations before real applicant use

Render Free can sleep/restart and is documented by Render as unsuitable for
production applications. Treat this release as a limited pilot. Original CV
files are not persisted; encrypted parsed text/history remain in Neon.

Gemini is still explicitly sample-data-only. Moving storage to Neon does not
authorize sending real CVs to Gemini's unpaid API. Select/configure a suitable
processor before real applicant AI processing.

Production email signup/login requires verified email. Until email delivery is
configured, public signup fails explicitly and unverified local accounts need
verification before production password login. Configure Google OAuth's final
HTTPS JavaScript origin separately. Google sign-in does not silently attach to an
existing password account by matching email.

Render Free blocks common outbound SMTP ports; choose a supported HTTPS email
delivery integration or an appropriate hosting/mail setup before enabling public
signup/recovery. The current SMTP transport is not a complete free Render email
solution. No mailbox credentials were created or real verification emails sent.

## Migration performed

The local PostgreSQL tables were rehearsed on an expiring Neon branch, then copied
to the main branch with exact row/ciphertext comparisons and decryption checks.
The original local PostgreSQL database, encrypted backup and private rollback
connection file were retained. The local app's default connection now points to
Neon. The rehearsal branch expires automatically; it was not made the default.

Reverting only the local connection does not copy any new cloud writes back to
the old database. Stop writes and take a new encrypted backup before rollback.
Keep the external encryption key backed up separately from the database.

## Verification

After a deploy reaches `live`, check `/`, `/health`, `/api/auth/config` and an
unauthenticated `/api/session` (must be 401). Verify the login page's CSP, no-store
headers and secure cookie behavior. Any synthetic smoke account must be removed
after verification; never print password, key, DB URL or applicant content.
