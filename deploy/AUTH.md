# Accounts, sign-in and email recovery

The React access-token screen has been replaced with email/password signup,
login, forgot/reset password, email verification and Google Identity Services.
The authentication tables are added automatically on API startup, preserving
existing user IDs, saved jobs, CV text, encryption keys and screening history.

## Local use

Open http://127.0.0.1:5173 and choose **Create an account**. Use a unique password
of at least 8 characters with uppercase, lowercase, a number and a special character.
Signup requires first name, last name, date of birth and matching password confirmation.
First/last name and DOB are encrypted inside the existing account profile field;
old profiles remain readable. DOB is not included in candidate matching or AI prompts.
Without SMTP, local signup works immediately and
email verification is pending. Once SMTP is configured, verification is required.
Production registration requires SMTP and verified email before email login.
The Google button and email recovery show setup status until configured.

Passwords use Argon2id (64 MiB, 3 iterations). Sessions expire after 12 hours,
live in HttpOnly SameSite=Lax cookies, and use Secure cookies in production.
Only session/recovery token hashes are stored. Browser localStorage/sessionStorage
never stores passwords or session tokens. Logout revokes the current session;
resetting a password revokes all sessions and the old legacy bearer credential.
Mutating cookie requests require an allowed Origin and X-CSRF-Protection header.
The browser and API must use the same hostname locally (127.0.0.1 or localhost).
Production must serve the API on the frontend origin with HTTPS.

Account email addresses and Google subject IDs are searchable account metadata.
Display names, jobs and CV data are encrypted with the existing external key.
Encrypted database backup/restore now includes account/session/recovery tables.
Old backups are accepted with empty authentication tables; restoring an old
backup does not restore passwords created later. Protect recovery backups too.

## Keep an existing recruiter's saved data

Creating a new account creates a new isolated workspace. To attach email login
to an existing administrator-created user **without changing its owner ID**:

```powershell
cd E:\CV-Shortlisted\backend
.\.venv\Scripts\python.exe setup_account.py --legacy-name recruiter
```

Enter email and password at the local prompts. The local administrator attests
email ownership. This does not merge accounts and never overwrites an existing
email login. Legacy bearer credentials remain API-compatible until revoked;
they are not used anywhere in the new frontend. Do not create a duplicate account
with the intended email before attaching it to your existing recruiter account.

## Google sign-in

1. In Google Cloud Console, configure Google Auth Platform/consent branding,
   audience and any required test users for your project.
2. Create an OAuth **Web application** client. A Gemini API key is not an OAuth
   Client ID. Add authorized JavaScript origins:
   `http://127.0.0.1:5173` and `http://localhost:5173` for development, plus the
   exact HTTPS domain for deployment. This popup ID-token flow does not require
   a client secret or a redirect URI in our backend.
3. Run `python setup_auth.py` using the project venv; enter the Web Client ID.
   It creates `%LOCALAPPDATA%\CVShortlisted\secrets\auth.credentials.json` with
   a current-user-only Windows ACL. `AUTH_CONFIG_FILE` can select a mounted
   production secret file. Never put SMTP passwords in frontend VITE variables.
4. Refresh the page. Google loads only when configured. The server verifies
   Google's signature, audience, issuer, expiry, verified email, and a browser-bound
   five-minute single-use nonce. No Google access/refresh token is stored.

For Google-only setup (or updating an existing Client ID without changing SMTP),
run `.\.venv\Scripts\python.exe setup_google.py` from the backend folder.
Paste the public Web Client ID at its prompt. The script preserves existing
private email settings and atomically replaces the restricted configuration file.

Existing email/password accounts are not silently linked by matching email.
Use password sign-in for those accounts. Google Gmail/Workspace addresses are
accepted as Google-authoritative; other addresses require our own email
verification via SMTP before their first session.

## SMTP / forgot password

Use an SMTP provider with verified sender and TLS (587 STARTTLS or 465 SSL).
Set these private JSON fields with `setup_auth.py` or edit the existing private
file locally (never paste its contents in chat):

```json
{
  "app_url": "http://127.0.0.1:5173",
  "google_client_id": "YOUR_WEB_CLIENT_ID.apps.googleusercontent.com",
  "smtp_host": "YOUR_SMTP_HOST",
  "smtp_port": 587,
  "smtp_from": "YOUR_VERIFIED_SENDER",
  "smtp_username": "YOUR_SMTP_USERNAME",
  "smtp_password": "YOUR_PRIVATE_SMTP_PASSWORD"
}
```

`app_url` must exactly match an allowed frontend origin, with no path/query.
Remove placeholder fields for a service you have not configured. Reset and
verification links expire in 30 minutes and are single use. Tokens travel in URL
fragments, are removed from browser history immediately, and never appear in
server access logs. Recovery responses do not reveal whether the account exists.
Reset does not automatically log in. No email is sent until you request a signup,
resend or recovery operation; setup/testing does not contact real recipients.

For hosting, set the host `AUTH_CONFIG_FILE` to your private configuration JSON.
Compose mounts it as `/run/secrets/screener_auth`. The API has outbound network
access for Google certificate verification and SMTP; no API port is published.
Caddy's CSP permits Google's required GIS
origins and uses COOP same-origin-allow-popups. Configure real HTTPS origins,
SMTP and Google client origins before exposing the app publicly. The existing
single-worker rate limiter bounds local auth attempts; multi-worker deployments
need a shared limiter. This change does not deploy the project.

Tests cover account isolation, hashing, CSRF, session expiry/logout, reset reuse,
session revocation, verification, Google nonce replay and email collision. Google
and mail in integration tests are mocked; real OAuth/SMTP still need your setup.

References:
- https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
- https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
- https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
