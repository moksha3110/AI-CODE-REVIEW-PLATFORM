# AI Analysis Service

Consumes `analysis.requested` events, fetches the exact changed files a push
touched, sends each one to Claude for a structured code review, and
publishes `review.completed` for the (not-yet-built) Review Service to
persist. It's a background worker first, an HTTP service only for
`/healthz`, `/readyz`, and `/metrics`.

## Pipeline

```
RabbitMQ (analysis.requested)
  -> claim/dedupe against analysis_runs (idempotent + retry ledger)
  -> Repository Service /internal/installations/{id}/token  (mint clone token)
  -> git fetch --depth 1 origin <after_sha>                 (clone the code)
  -> Claude, per changed file, structured JSON output        (AI review)
  -> analysis_runs row + outbox_events row, one transaction  (transactional outbox)
  -> outbox relay -> RabbitMQ (review.completed)
```

## What's implemented

- **Idempotent, retryable consumption**: a unique constraint on
  `analysis_runs.push_event_id` means a redelivered or duplicate message
  converges onto the same row instead of running the AI twice. A failed run
  is requeued (`nack(requeue=True)`) up to `MAX_ANALYSIS_ATTEMPTS`, then
  dropped rather than looped on forever.
- **No GitHub App credential of its own**: clone tokens come from Repository
  Service's internal API, keeping exactly one service holding that private
  key.
- **Structured AI output**: Claude is called with `output_config.format`
  (structured outputs), not "please reply with JSON" prompting - the
  response is guaranteed to match the review schema.
- **Transactional outbox**: same pattern as Repository Service - the
  completed run and the `review.completed` event are written in one
  transaction, relayed to RabbitMQ by a background task.

## Running locally

```bash
cp .env.example .env      # fill in ANTHROPIC_API_KEY
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8002
```

Requires Postgres, RabbitMQ, and a running Repository Service (for the
installation-token endpoint) - see the root `docker-compose.yml`.

## Known gaps / honest trade-offs

- The RabbitMQ consumer and the outbox relay both run as background asyncio
  tasks inside this one process, same documented trade-off as Repository
  Service's outbox relay - at real scale each becomes its own deployable.
- The installation token is passed to `git` via the remote URL
  (`https://x-access-token:<token>@...`), which means it briefly appears in
  that subprocess's argv and could be visible to `ps` on a compromised host.
  A hardened version would use `GIT_ASKPASS` or a short-lived credential
  helper instead.
- Files are read as UTF-8 text with a size cap; anything binary or over the
  cap is silently skipped rather than reviewed - reasonable for a code
  reviewer, but worth knowing if a change looks "not reviewed" in the
  dashboard.
- No dead-letter table for messages that exhaust their retry budget - they're
  dropped and logged, same gap as Repository Service's outbox relay.
