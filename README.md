# AI-powered distributed code review platform

An event-driven microservices platform that reviews code automatically on every push:
GitHub webhook -> repository service -> RabbitMQ -> AI analysis service -> review
service + notification service -> Postgres -> Next.js dashboard.

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
| 4. Notification Service | **Implemented** - independent consumer of review.completed, resolves repo owner via Repository Service, REST API for in-app notifications |
| 4. Dashboard Service / frontend | **Implemented** - Next.js app: auth, repositories list, repository detail (review history + quality-trends chart), review detail (per-file findings), notifications bell |
| 5. Docker Compose | **Implemented** - all six services + postgres/redis/rabbitmq wired |
| 6. Kubernetes | **Implemented** - plain YAML for all six services + in-cluster postgres/redis/rabbitmq, verified end-to-end against a local minikube cluster (see `k8s/README.md`) |
| 7. AWS deployment | **Implemented and live** - real EKS cluster, AWS Load Balancer Controller installed, all 6 images pushed to ECR, real GitHub OAuth App + GitHub App + Anthropic credentials wired, public URL reachable (sslip.io - see `k8s/README.md`) |
| 8. Terraform | **Applied** - VPC + EKS cluster + node group + ECR repos + ALB Controller IRSA, all provisioned for real via `terraform apply` (see `terraform/README.md`) |
| 9-10. CI/CD, monitoring | Not started |

## Repo layout

```
services/
  auth-service/            FastAPI service: GitHub OAuth + JWT issuance
  repository-service/      FastAPI service: webhooks, GitHub App auth, outbox -> RabbitMQ
  ai-analysis-service/     Background worker: RabbitMQ consumer, git fetch, Claude review, outbox -> RabbitMQ
  review-service/          FastAPI service: RabbitMQ consumer + REST API for review history/detail/trends
  notification-service/    FastAPI service: RabbitMQ consumer + REST API for in-app notifications
  dashboard-service/       Next.js frontend: auth, repositories, review/quality-trend views, notifications
libs/
  shared_auth/             Installable package every service uses to verify JWTs locally
k8s/                       Kubernetes manifests: all six services + in-cluster postgres/redis/rabbitmq
terraform/                 AWS infra (VPC, EKS, ECR) for running k8s/ on a real cluster
docker-compose.yml         Local dev: postgres, redis, rabbitmq, all six services
```

## Event flow

```
GitHub push
  -> repository-service: verify webhook signature, persist PushEvent
  -> outbox -> RabbitMQ "analysis.requested"
  -> ai-analysis-service: fetch installation token from repository-service,
     git fetch the exact commit, review each changed file with Claude
  -> outbox -> RabbitMQ "review.completed"
  -> review-service: persist Review + FileReview rows        (own queue)
  -> notification-service: resolve the repo's owner via       (own queue)
     repository-service, persist a Notification for them
  -> dashboard-service queries review-service's and
     notification-service's REST APIs directly from the browser
```

review-service and notification-service both bind their own queue to the
same `review.completed` routing key on the shared topic exchange - a real
pub-sub fan-out, not a chain. Neither service knows the other exists.

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
cp services/notification-service/.env.example services/notification-service/.env
cp services/dashboard-service/.env.local.example services/dashboard-service/.env.local
# fill in GITHUB_CLIENT_ID/SECRET, GITHUB_APP_*, and ANTHROPIC_API_KEY in the respective .env files
docker compose up --build
```

| Service | Port | Swagger |
|---|---|---|
| auth-service | 8000 | http://localhost:8000/docs |
| repository-service | 8001 | http://localhost:8001/docs |
| ai-analysis-service | 8002 | http://localhost:8002/docs (health/metrics only - no public API) |
| review-service | 8003 | http://localhost:8003/docs |
| notification-service | 8004 | http://localhost:8004/docs |
| dashboard-service | 3000 | http://localhost:3000 |

Prometheus metrics are exposed at `/metrics` on every service.

## Running tests

```bash
cd services/<service-name>
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
pytest -v
```

Every service's suite runs against an in-memory SQLite DB (and fakeredis,
where a service uses Redis) - no external services required. All five
suites are green as of this commit (`auth-service`: 7 passed,
`repository-service`: 9 passed, `ai-analysis-service`: 8 passed,
`review-service`: 8 passed, `notification-service`: 13 passed).

## Known gaps / honest trade-offs (worth being able to discuss in an interview)

- **Outbox relays and RabbitMQ consumers run as background asyncio tasks
  inside the same process** as each service's API, in repository-service,
  ai-analysis-service, review-service, and notification-service. At real
  scale each becomes its own deployable so it can be restarted/scaled
  independently - `run_outbox_relay`/`run_consumer` are already written to
  be portable to a standalone worker with no code changes.
- **No dead-letter table.** A row that keeps failing to publish (outbox
  relay), or a message that exhausts `MAX_ANALYSIS_ATTEMPTS` (AI Analysis
  Service's consumer), is dropped/logged rather than parked somewhere for
  manual replay. Notification Service has no attempts ledger at all - see
  its own README.
- **No repository-ownership check in Review Service.** Its REST API
  authenticates the caller but doesn't verify they own the `repository_id`
  they're querying - that check lives in Repository Service's user-scoped
  `GET /repositories`. A real dashboard/BFF would only pass IDs it already
  fetched that way. (Notification Service *does* enforce this, scoping
  every query to the authenticated user - the difference is that Review
  Service has no independent way to know who owns a `repository_id` short
  of a network call to Repository Service on every request, while
  Notification Service resolves ownership once, at ingest time, and stores
  it.)
- **No real notification delivery channel.** Notification Service writes
  in-app rows only - no email, Slack, or push.
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
- **Dashboard auth relies on React effect-ordering, not just network
  timing.** The frontend keeps its access token in memory only (never
  `localStorage`) and restores it via a silent refresh against an
  httpOnly cookie on mount. Because the OAuth callback page's effect fires
  before `AuthProvider`'s own mount effect (child effects run before
  parent effects in React), a naive implementation can race the two and
  land in a permanently inconsistent state (`accessToken` cleared by a
  losing refresh call while `user` gets set by the callback's fetch). Fixed
  with a synchronous ref flag the mount effect checks before attempting a
  refresh at all - see `services/dashboard-service/src/lib/auth-context.tsx`.
  Any future change to this file should be tested by loading
  `/auth/callback#access_token=...` as a fresh page load, not a
  client-side navigation, since that's the exact scenario that exposed the
  bug.
- **No automated frontend tests.** Dashboard Service was verified manually
  through the browser (see its own README) rather than with a Vitest/RTL
  or Playwright suite - the one place in the platform where "tested" means
  "manually exercised," not "has a green CI-style test run."
