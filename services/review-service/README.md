# Review Service

Persists AI-generated code reviews and exposes the REST API the dashboard
uses for repository history and quality trends. Consumes
`review.completed` off RabbitMQ; everything else is a read-only, JWT-
protected API.

## What's implemented

- **Idempotent ingestion**: a unique constraint on `reviews.push_event_id`
  means a redelivered or duplicate `review.completed` message converges
  onto the same row instead of double-counting.
- **Denormalized counts**: `total_bug_count`/`total_security_issue_count`
  on `reviews`, and the per-file equivalents on `file_reviews`, are computed
  once at ingest time so the quality-trends endpoint aggregates with plain
  SQL instead of unpacking JSON per row on every request.
- **REST API** (JWT-protected via `shared_auth`):
  - `GET /api/v1/repositories/{id}/reviews` - paginated, newest-first
  - `GET /api/v1/reviews/{id}` - full detail, including every file's
    bugs/security issues/optimizations/documentation suggestions
  - `GET /api/v1/repositories/{id}/quality-trends` - oldest-first complexity
    and bug-count series, for the dashboard's chart

## Running locally

```bash
cp .env.example .env
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8003
```

Requires Postgres and RabbitMQ - see the root `docker-compose.yml`. Needs
Auth Service's public key mounted the same way Repository Service does.

## Known gaps / honest trade-offs

- **No repository-ownership check.** Authentication proves who's asking,
  not that they own the `repository_id` they're querying - that check
  lives in Repository Service's own user-scoped `GET /repositories`
  listing. A real dashboard/BFF would only ever pass IDs it already fetched
  that way; this service trusts the caller on that point rather than making
  a network call back to Repository Service on every request.
- **RabbitMQ consumer runs as a background asyncio task** inside this same
  process, same documented trade-off as the other services' consumers/relays.
- **Quality trends are unpaginated** - fine for a repo's lifetime review
  count at this project's scale, would need pagination or downsampling for
  a repo with years of history.
