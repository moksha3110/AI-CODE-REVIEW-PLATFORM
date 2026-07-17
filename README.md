# AI-powered distributed code review platform

An event-driven microservices platform that reviews code automatically on every push:
GitHub webhook -> repository service -> RabbitMQ -> AI analysis service -> review
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
| 4. AI Analysis Service | **Implemented** - consumes push events, clones changed files, Claude structured-output review, transactional outbox -> RabbitMQ |
| 4. Review Service | **Implemented** - consumes review.completed, persists reviews + file reviews, REST API for history/detail/quality-trends |
| 4. Notification Service | Not started |
| 4. Dashboard Service / frontend | Not started |
| 5-10. Docker/K8s/AWS/Terraform/CI/monitoring | Not started |

## Repo layout

```
services/
  auth-service/            FastAPI service: GitHub OAuth + JWT issuance
  repository-service/      FastAPI service: webhooks, GitHub App auth, outbox -> RabbitMQ
  ai-analysis-service/     Background worker: RabbitMQ consumer, git fetch, Claude review, outbox -> RabbitMQ
  review-service/          FastAPI service: RabbitMQ consumer + REST API for review history/detail/trends
libs/
  shared_auth/             Installable package every service uses to verify JWTs locally
docker-compose.yml         Local dev: postgres, redis, rabbitmq, all four services
```

## Event flow

```
GitHub push
  -> repository-service: verify webhook signature, persist PushEvent
  -> outbox -> RabbitMQ "analysis.requested"
  -> ai-analysis-service: fetch installation token from repository-service,
     git fetch the exact commit, review each changed file with Claude
  -> outbox -> RabbitMQ "review.completed"
  -> review-service: persist Review + FileReview rows
  -> dashboard (not yet built) queries review-service's REST API
```

## Running locally

Each service needs its own `.env` (copy from `.env.example`), a venv, and
`alembic upgrade head` against a running Postgres - see each service's own
README for specifics. Quickest path is Docker Compose from the repo root:

```bash
./services/auth-service/scripts/generate_keys.sh   # RSA keypair auth-service signs JWTs with
cp services/auth-service/.env.example services/auth-service/.env
cp services/repository-service/.env.example services/repository-service/.env
cp services/ai-analysis-service/.env.example services/ai-analysis-service/.env
cp services/review-service/.env.example services/review-service/.env
# fill in GITHUB_CLIENT_ID/SECRET, GITHUB_APP_*, and ANTHROPIC_API_KEY in the respective .env files
docker compose up --build
```

| Service | Port | Swagger |
|---|---|---|
| auth-service | 8000 | http://localhost:8000/docs |
| repository-service | 8001 | http://localhost:8001/docs |
| ai-analysis-service | 8002 | http://localhost:8002/docs (health/metrics only - no public API) |
| review-service | 8003 | http://localhost:8003/docs |

Prometheus metrics are exposed at `/metrics` on every service.

## Running tests

```bash
cd services/<service-name>
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
pytest -v
```

Every service's suite runs against an in-memory SQLite DB (and fakeredis,
where a service uses Redis) - no external services required. All four
suites are green as of this commit (`auth-service`: 7 passed,
`repository-service`: 6 passed, `ai-analysis-service`: 8 passed,
`review-service`: 8 passed).

## Known gaps / honest trade-offs (worth being able to discuss in an interview)

- **Outbox relays and RabbitMQ consumers run as background asyncio tasks
  inside the same process** as each service's API, in repository-service,
  ai-analysis-service, and review-service. At real scale each becomes its
  own deployable so it can be restarted/scaled independently -
  `run_outbox_relay`/`run_consumer` are already written to be portable to a
  standalone worker with no code changes.
- **No dead-letter table.** A row that keeps failing to publish (outbox
  relay), or a message that exhausts `MAX_ANALYSIS_ATTEMPTS` (AI Analysis
  Service's consumer), is dropped/logged rather than parked somewhere for
  manual replay.
- **No repository-ownership check in Review Service.** Its REST API
  authenticates the caller but doesn't verify they own the `repository_id`
  they're querying - that check lives in Repository Service's user-scoped
  `GET /repositories`. A real dashboard/BFF would only pass IDs it already
  fetched that way.
- **`rotate_refresh_token`** (auth-service) issues the new token pair and
  revokes the old one in two separate commits on the same session, not one
  atomic transaction. Low risk (same session, sequential awaits) but the
  correct fix is wrapping both in an explicit `async with db.begin():` block.
- **`with_for_update(skip_locked=True)`** (both outbox relays) is a
  Postgres-only feature; SQLite (used in tests) silently ignores it rather
  than erroring, so the *locking* behavior specifically is only validated
  against real Postgres, not by the test suite.
- **AI Analysis Service passes the GitHub installation token to `git` via
  the remote URL** (`https://x-access-token:<token>@...`), so it briefly
  appears in that subprocess's argv. A hardened version would use
  `GIT_ASKPASS` or a credential helper instead.
- **The installation callback** (repository-service) trusts whatever GitHub
  sends back once OAuth `state` checks out; there's no additional
  verification that the account being installed matches anything about the
  connecting user beyond that.
