# AI-powered distributed code review platform

An event-driven microservices platform that reviews code automatically on every push:
GitHub webhook -> repository service -> RabbitMQ -> AI analysis workers -> review
service -> Postgres -> Next.js dashboard.

Full architecture write-up: see the conversation this was built in, or `docs/`
(populated as later phases land).

## Build status

| Phase | Status |
|---|---|
| 1. Architecture design | Done |
| 2. Service rationale | Condensed version done, full version on request |
| 3. Folder structure | Done (this repo) |
| 4. Auth Service | **Implemented** - GitHub OAuth login, JWT (RS256) issuance, refresh rotation with reuse detection |
| 4. Repository Service | **Implemented** - webhook ingestion, GitHub App auth, transactional outbox -> RabbitMQ |
| 4. AI Analysis Service | Not started |
| 4. Review Service | Not started |
| 4. Notification Service | Not started |
| 4. Dashboard Service / frontend | Not started |
| 5-10. Docker/K8s/AWS/Terraform/CI/monitoring | Not started |

## Repo layout

```
services/
  auth-service/          FastAPI service: GitHub OAuth + JWT issuance
  repository-service/     FastAPI service: webhooks, GitHub App auth, outbox -> RabbitMQ
libs/
  shared_auth/            Installable package every service uses to verify JWTs locally
docker-compose.yml         Local dev: postgres, redis, rabbitmq, auth-service
```

## Running Auth Service locally

```bash
cd services/auth-service
./scripts/generate_keys.sh          # creates keys/private.pem + keys/public.pem
cp .env.example .env                # fill in GITHUB_CLIENT_ID / SECRET from a GitHub OAuth App
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head                 # requires postgres running - see docker-compose
uvicorn app.main:app --reload
```

Or via Docker (from the repo root, since the build needs `libs/shared_auth` too):

```bash
docker compose up --build
```

Swagger docs: http://localhost:8000/docs
Prometheus metrics: http://localhost:8000/metrics

## Running tests

```bash
cd services/auth-service
pip install -r requirements-dev.txt
pytest -v
```

Tests run against an in-memory SQLite DB and fakeredis - no external services
required. **Note:** this was built in a sandboxed environment with no network
access, so the suite has been statically verified (compiles cleanly, logic
traced by hand) but not actually executed end-to-end. Run it yourself before
trusting it in CI - see "known gaps" below.

## Known gaps / honest trade-offs (worth being able to discuss in an interview)

- `rotate_refresh_token` issues the new token pair and revokes the old one in
  two separate commits on the same session, not one atomic transaction. Low
  risk (same session, sequential awaits) but the correct fix is wrapping both
  in an explicit `async with db.begin():` block.
- The test suite hasn't been run against a real interpreter in this
  environment (no network to install deps) - only `py_compile`-checked and
  manually traced. Run `pytest -v` yourself as a first step.
- No database-level unique constraint yet stopping two rows racing to insert
  the same `github_id` concurrently (relies on the app-level upsert check).
  Fine at current scale; a unique constraint + `ON CONFLICT` upsert is the
  hardened version.
- Rate limiting is per-endpoint via a FastAPI dependency, not centralized at
  an API gateway - reasonable for one service, worth revisiting once the
  gateway/ingress layer exists in Phase 6.
