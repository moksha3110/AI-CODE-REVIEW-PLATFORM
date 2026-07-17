# Notification Service

Consumes `review.completed` off RabbitMQ and notifies the repository's
owning user - in-app notifications for now, exposed via a JWT-protected
REST API. It's Review Service's sibling on the event bus, not its
downstream: both consume the same event independently, on separate
queues, and neither knows the other exists.

## Why it needs Repository Service

`review.completed` carries `repository_id` but not "who owns this repo" -
that mapping (repository -> installation -> connecting user) lives in
Repository Service. This service added a small internal endpoint there
(`GET /api/v1/internal/repositories/{id}/owner`) rather than duplicating
Installation data locally, keeping repository ownership as Repository
Service's exclusive concern.

## What's implemented

- **Idempotent ingestion**: a unique constraint on
  `notifications.push_event_id` means a redelivered or duplicate
  `review.completed` message converges onto the same row instead of
  double-notifying.
- **Distinct failure handling in the consumer**: a schema mismatch
  (`MalformedReviewPayloadError`) is acked and dropped - retrying a parse
  error never helps. A transient failure (owner lookup down, DB hiccup) is
  nacked and requeued so RabbitMQ redelivers it.
- **REST API** (JWT-protected via `shared_auth`):
  - `GET /api/v1/notifications` - paginated, newest-first, scoped to the
    authenticated user, with an `unread_only` filter and an `unread_count`
    in every response (enough for a notification-bell badge without a
    second request)
  - `POST /api/v1/notifications/{id}/read` - marks read; 404s identically
    whether the id doesn't exist or belongs to someone else, so it can't be
    used to enumerate other users' notification ids

## Running locally

```bash
cp .env.example .env
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8004
```

Requires Postgres, RabbitMQ, and a running Repository Service (for the
owner-lookup endpoint) - see the root `docker-compose.yml`.

## Known gaps / honest trade-offs

- **No real delivery channel.** Notifications are in-app rows only - no
  email, Slack, or push. Adding one would mean a new field
  (`channel`/`delivered_at`) and a delivery worker; the event-driven shape
  here already supports that without touching the ingestion path.
- **RabbitMQ consumer runs as a background asyncio task** inside this same
  process, same documented trade-off as the other services' consumers.
- **No retry-budget ledger** (unlike AI Analysis Service's
  `analysis_runs.attempts`) - a message that fails forever (e.g.
  Repository Service permanently down) redelivers indefinitely rather than
  eventually landing in a dead-letter queue. Reasonable here since the
  only failure modes are a transient network blip or a genuine data-
  integrity problem that redelivery won't fix either way, but worth
  hardening before this ran unattended in production.
