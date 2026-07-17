from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id_dep
from app.core.config import get_settings
from app.core.exceptions import NotificationNotFoundError
from app.db.session import get_db
from app.models.notification import Notification
from app.schemas.notification import NotificationOut, PaginatedNotificationsOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=PaginatedNotificationsOut)
async def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id_dep),
):
    settings = get_settings()
    page_size = min(limit or settings.default_page_size, settings.max_page_size)
    user_uuid = uuid.UUID(user_id)

    base_filter = Notification.user_id == user_uuid
    if unread_only:
        base_filter = base_filter & Notification.read_at.is_(None)

    total_result = await db.execute(select(func.count()).select_from(Notification).where(base_filter))
    total = total_result.scalar_one()

    unread_result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_uuid, Notification.read_at.is_(None))
    )
    unread_count = unread_result.scalar_one()

    result = await db.execute(
        select(Notification)
        .where(base_filter)
        .order_by(Notification.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    notifications = result.scalars().all()

    return PaginatedNotificationsOut(
        items=[NotificationOut.model_validate(n) for n in notifications],
        total=total,
        unread_count=unread_count,
        limit=page_size,
        offset=offset,
    )


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id_dep),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == uuid.UUID(user_id)
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        # Same 404 whether the id doesn't exist or belongs to someone else -
        # don't leak which one it is.
        raise NotificationNotFoundError(f"no notification with id={notification_id}")

    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()

    return notification
