# Deploy on a server you control

Use a real domain with DNS pointing to the server and inbound TCP 80/443 available. Install Docker Engine and Docker Compose. Use an encrypted server disk/volume and restrict operator access. The source package contains no real account tokens, CVs or database.

From `resume-screener`:

```sh
cp deploy/production.env.example .env.production
```

Edit APP_DOMAIN to your domain (for example `screening.your-company.com`). Keep RETENTION_SECONDS at the shortest appropriate duration (60–86400 seconds; default 3600). Do not put credentials in this file.

```sh
docker compose --env-file .env.production build
docker compose --env-file .env.production config
docker compose --env-file .env.production run --rm gateway caddy validate --config /etc/caddy/Caddyfile
docker compose --env-file .env.production up -d
```

Caddy requests/renews TLS certificates and serves the UI and `/api/*` under `https://<APP_DOMAIN>`. Use that HTTPS URL directly, including for API clients; do not POST candidate data to HTTP and rely on a redirect. Caddy's certificate issuance requires outgoing network, correct DNS and reachable validation ports. The API is isolated on an internal Docker network and has no published port or outbound internet access. Caddy alone bridges the public and private networks.

Create a distinct user token from the server terminal:

```sh
docker compose --env-file .env.production exec api python manage.py create-user recruiter
```

Give the printed token privately to that user. The token is displayed once; the database holds only its hash. Revoke a token and delete its saved exports:

```sh
docker compose --env-file .env.production exec api python manage.py revoke-user recruiter
```

Force an expired-row cleanup:

```sh
docker compose --env-file .env.production exec api python manage.py purge
```

Verify on the target host:

1. Open HTTPS and confirm its certificate is valid. Verify sign-in, parse/match/review/export on synthetic documents before real CVs.
2. `/health` works; unauthenticated `/api/session` returns 401. A second account cannot export/review/delete the first account's snapshot.
3. Confirm only ports 80/443 are exposed. The API container must not be directly reachable externally.
4. Confirm the same-origin API uses HTTPS, downloads have no-store headers, and HTTP API requests are not accepted as a data flow.
5. Test expiry and deletion and confirm downloaded copies remain under the user's control.
6. Run the included tests/build and validate the Caddy/Compose files before using the deployment. Review dependencies/images with your deployment scanner and pin approved image digests/runtime lock versions for your release; no vulnerability scan or external penetration test was performed here.

The private Docker subnet is `172.30.0.0/24`; Caddy has `172.30.0.2` and the API trusts forwarded scheme/client information only from that address. If changing the subnet, update **both** Compose and Dockerfile's `--forwarded-allow-ips`. Never use a wildcard trusted proxy list or publish the API port. Production APP_ENV requires exact ALLOWED_HOSTS and HTTPS CORS_ORIGINS and checks the trusted ASGI scheme. See [FastAPI proxy guidance](https://fastapi.tiangolo.com/advanced/behind-a-proxy/) and [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).

Use one API worker/instance with this release. Rate buckets are bounded but process-local, and the parser concurrency limit is per process. Multi-instance operation needs a shared limiter/concurrency control and an appropriately managed database.

Data is in the `screener_data` Docker volume. The API image creates the mount directory for UID/GID 10001 with mode 0700; database files are 0600 on POSIX. If using a host bind mount instead, provision it with that owner and private permissions on an encrypted filesystem. SQLite secure deletion is not encryption or a promise of forensic erasure. Exclude this volume from general backups or manage backup access, encryption and expiry separately. Do not retain old volume snapshots indefinitely. Deleting an app snapshot does not erase backups, OS swap/crash dumps, original uploaded files on user devices or downloaded CSVs.

The gateway disables request/runtime logging; the app logs only fixed route templates and status/event codes. Uvicorn access/error logs are disabled by the provided logging config to avoid unsanitized request/exception data. This trades detailed diagnostics for privacy; use sanitized application health/status events rather than enabling raw access/body logs. Do not enable debug mode.

The API container runs unprivileged, read-only, without Linux capabilities, with no-new-privileges, a private network, a small tmpfs, 1 GiB container memory, one CPU and 64 process/thread limit. Per-parser limits and a wall deadline add containment, but this is not a complete native-code sandbox or malware scanner. Keep the OS, Python, parser and proxy patched. Target-host TLS, container isolation, encrypted storage and dependency scanning must be verified by the operator; these cannot be certified from source-only tests.
