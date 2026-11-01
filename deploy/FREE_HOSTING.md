# Free hosting decision for the current application

Requested target: real CVs, no existing hosting/domain, initially $0 budget.
The app is not publicly deployed. Creating accounts and choosing a live data
processor remain necessary; no real applicant data has been transferred.

## Practical no-cost pilot

- Render Free can host a Python web service and a static frontend with managed
  HTTPS/provider subdomains. Its own documentation says not to use free instances
  for production applications. It sleeps after 15 minutes, can restart, and has
  ephemeral local storage. There is no availability guarantee for this proposal.
- Neon Free offers persistent PostgreSQL. Use an external database, not Render's
  expiring free PostgreSQL database. Confirm current storage/compute limits in
  the chosen Neon account before migrating any data.
- Keep existing field encryption. Supply a backed-up key through a platform
  secret file; never generate a replacement at each restart or commit it to Git.
- The current Gemini adapter explicitly allows only sample/fake data. It cannot
  be switched to real applicants by hiding the confirmation checkbox. Google's
  unpaid-service data-use terms must be reviewed before any real CV transfer.
- Groq offers a rate-limited Free plan and documents ZDR availability for all
  customers. This is a potential alternative processor, not an integrated or
  approved production provider yet. It needs explicit selection, private API key
  setup, ZDR configuration, a separate adapter and evaluation against this app's
  structured schemas. No real data should be sent to test provider setup.

The existing Compose deployment targets a VPS, not Render. Render deployment
still needs an adapted single-origin web entrypoint (to retain cookie/CSRF
security), platform proxy handling, static frontend serving, secret provisioning
and memory/concurrency checks. Do not paste the current VPS Compose commands into
a free Render service and expect a working production deployment.

Email verification and password recovery also need configured email delivery;
Google sign-in needs a Web OAuth client with the final HTTPS origin. Local users
and CV history should be migrated only through verified encrypted backup/restore
with the original key, after the target has passed synthetic-account tests.

## Next external setup

Create Render and Neon accounts using their Free plans. Do not enter payment
credentials or upgrade plans merely to follow this proposal. A managed provider
subdomain is enough to start; a purchased domain is optional. Confirm whether a
limited pilot is acceptable versus a production service with availability and
backup requirements. Choose the AI processor separately before uploading CVs.

References checked 2026-10-30:
- https://render.com/docs/free
- https://render.com/docs/your-first-deploy
- https://neon.com/blog/neon-free-plan-1-gb-per-project
- https://ai.google.dev/gemini-api/terms
- https://console.groq.com/docs/your-data
- https://console.groq.com/docs/rate-limits
