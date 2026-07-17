from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user_id_dep
from app.core.config import get_settings
from app.core.exceptions import ReviewNotFoundError
from app.db.session import get_db
from app.models.review import Review
from app.schemas.review import (
    PaginatedReviewsOut,
    QualityTrendPointOut,
    ReviewDetailOut,
    ReviewSummaryOut,
)

router = APIRouter(tags=["reviews"])


@router.get("/repositories/{repository_id}/reviews", response_model=PaginatedReviewsOut)
async def list_reviews(
    repository_id: uuid.UUID,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id_dep),
):
    """
    Newest-first review history for a repository, for the dashboard's
    "review history" list. Authentication proves who's asking; it does not
    (yet) prove the caller owns `repository_id` - that check lives in
    Repository Service's own user-scoped listing, and a real dashboard
    would only ever pass IDs it already fetched that way. See README.
    """
    settings = get_settings()
    page_size = min(limit or settings.default_page_size, settings.max_page_size)

    count_result = await db.execute(
        select(func.count()).select_from(Review).where(Review.repository_id == repository_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Review)
        .where(Review.repository_id == repository_id)
        .order_by(Review.analyzed_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    reviews = result.scalars().all()

    return PaginatedReviewsOut(
        items=[ReviewSummaryOut.model_validate(r) for r in reviews],
        total=total,
        limit=page_size,
        offset=offset,
    )


@router.get("/reviews/{review_id}", response_model=ReviewDetailOut)
async def get_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id_dep),
):
    result = await db.execute(
        select(Review).options(selectinload(Review.file_reviews)).where(Review.id == review_id)
    )
    review = result.scalar_one_or_none()
    if review is None:
        raise ReviewNotFoundError(f"no review with id={review_id}")
    return review


@router.get("/repositories/{repository_id}/quality-trends", response_model=list[QualityTrendPointOut])
async def get_quality_trends(
    repository_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id_dep),
):
    """
    Oldest-first complexity/bug-count series for the dashboard's quality
    trend chart - deliberately unpaginated (a repo's review count over its
    lifetime is small enough to chart in one shot; revisit if that stops
    being true).
    """
    result = await db.execute(
        select(Review).where(Review.repository_id == repository_id).order_by(Review.analyzed_at.asc())
    )
    return result.scalars().all()
