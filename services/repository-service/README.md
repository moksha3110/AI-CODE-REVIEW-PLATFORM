# Repository service

Receives GitHub webhooks, manages GitHub App installations, and reliably
hands off push events to the AI analysis pipeline via RabbitMQ.

## What's implemented

- **Webhook ingestion** (`POST /api/v1/webhooks/github`) - HMAC-SHA256
  signature verification, push event parsing, idempotent processing.
- **Idempotency, two layers deep**: a Redis `SET NX` fast-path, backed by a
  real unique constraint on `push_events.github_delivery_id` for the rare
  race where two deliveries land concurrently.
- **Transactional outbox**: the push event row and the "please analyze this"
  event are written in one DB transaction. A background relay task drains
  unpublished outbox rows to RabbitMQ on a short interval, using
  `SELECT ... FOR UPDATE SKIP LOCKED` so it's safe to run more than one
  replica.
- **GitHub App auth**: a completely separate credential chain from Auth
  Service's OAuth login - see `app/core/github_app.py` for the JWT ->
  installation-token exchange, cached in Redis.
- **Internal API** (`GET /api/v1/internal/installations/{id}/token`) - lets
  AI Analysis Service request a fresh clone-capable token without ever
  holding the GitHub App private key itself.

## Two GitHub integrations, on purpose

| | Auth Service | Repository Service |
|---|---|---|
| GitHub integration type | OAuth App | GitHub App |
| Answers | "who is this human" | "which repos can we read, and can we get webhooks" |
| Credential | Auth Service's own JWT keypair | GitHub App private key |
| Revoked by | Auth Service session/refresh-token revocation | Uninstalling the App from a repo/org |

## Running locally

```bash
./scripts/generate_keys.sh   # if you haven't already run this in auth-service, do it there;
                              # this service needs a GitHub App private key, not this repo's own keypair -
                              # download that PEM from your GitHub App's settings page instead.
cp .env.example .env
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

Swagger docs: http://localhost:8001/docs

## Known gaps / honest trade-offs

- The outbox relay runs as a background asyncio task inside this same
  process. At real scale it should be its own deployable so it can restart
  and scale independently of the API - `run_outbox_relay` is already
  written to be portable to a standalone worker with no changes.
- A row that keeps failing to publish is retried forever with no backoff
  and no dead-letter table - fine for now, a real gap for production.
- `with_for_update(skip_locked=True)` is a Postgres-only feature. SQLite
  (used in tests) silently ignores it rather than erroring, so the relay's
  *locking* behavior specifically is only validated against real Postgres,
  not by the test suite - worth running the relay test manually against
  docker-compose's Postgres before trusting it fully.
- The installation callback trusts whatever GitHub sends back once `state`
  checks out; there's no additional verification that the account being
  installed matches anything about the connecting user beyond that.
