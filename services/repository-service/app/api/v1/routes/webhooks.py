from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis
from app.core.logging import get_logger
from app.core.webhook_security import verify_signature
from app.db.session import get_db
from app.services.webhook_processor import process_push_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger(__name__)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_github_delivery: str = Header(...),
    x_hub_signature_256: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    Single entry point for every GitHub webhook event this App is
    subscribed to. Deliberately does the minimum possible work before
    returning 200 - GitHub expects a response within 10 seconds and will
    consider the delivery failed (and retry) otherwise. Anything beyond
    "persist + hand off to the outbox" belongs in the AI Analysis Service,
    triggered later via RabbitMQ, never here.
    """
    raw_body = await request.body()
    verify_signature(raw_body, x_hub_signature_256)
    payload = json.loads(raw_body)

    logger.info("webhook_received", github_event=x_github_event, delivery_id=x_github_delivery)

    if x_github_event == "ping":
        return {"status": "pong"}

    if x_github_event == "push":
        # GitHub also fires "push" for branch/tag deletions, where "after"
        # is all zeros - nothing to review in that case.
        if payload.get("after") == "0" * 40:
            return {"status": "acknowledged", "note": "branch/tag deletion, nothing to review"}

        push_event_id = await process_push_event(db, redis, x_github_delivery, payload)
        return {
            "status": "acknowledged",
            "processed": push_event_id is not None,
            "push_event_id": str(push_event_id) if push_event_id else None,
        }

    # installation / installation_repositories events are handled via the
    # authenticated /repositories/installations/callback flow instead, since
    # we need the connecting user's identity - a raw webhook alone can't
    # tell us "which of our platform users did this." We still ack so
    # GitHub doesn't treat it as a failed delivery and keep retrying.
    return {"status": "acknowledged", "note": f"event type '{x_github_event}' not processed here"}
