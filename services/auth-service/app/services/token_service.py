from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.core.exceptions import InvalidTokenError, TokenReuseDetectedError
from app.core.logging import get_logger
from app.models.refresh_token import RefreshToken

logger = get_logger(__name__)


def hash_jti(jti: str) -> str:
    # We store a hash of the jti, not the raw token, so a DB read alone
    # can't be replayed as a valid credential.
    return hashlib.sha256(jti.encode()).hexdigest()


async def issue_token_pair(db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID | None = None) -> dict:
    """Issues a fresh access + refresh token pair. Starts a new rotation
    family if none is given (i.e. this is an initial login, not a refresh)."""
    access = security.issue_access_token(str(user_id))
    refresh = security.issue_refresh_token(str(user_id))

    row = RefreshToken(
        id=uuid.uuid4(),
        jti=hash_jti(refresh.jti),
        family_id=family_id or uuid.uuid4(),
        user_id=user_id,
        expires_at=datetime.fromtimestamp(refresh.expires_at, tz=timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()

    return {
        "access_token": access.token,
        "refresh_token": refresh.token,
        "expires_in": get_settings().access_token_expire_minutes * 60,
        "token_type": "bearer",
    }


async def rotate_refresh_token(db: AsyncSession, presented_token: str) -> dict:
    """
    Validates a refresh token, and if it's unused, rotates it: issues a new
    pair and marks the old one as replaced. If the token was already used
    once before (replayed), that's a theft signal -> revoke the entire
    family and force the user to log in again everywhere.
    """
    try:
        payload = security.decode_token(presented_token, expected_type="refresh")
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("refresh token is invalid or expired") from exc

    jti_hash = hash_jti(payload["jti"])
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti_hash))
    stored = result.scalar_one_or_none()

    if stored is None:
        raise InvalidTokenError("refresh token not recognized")

    if stored.revoked_at is not None:
        # This exact token was already rotated away once - someone is
        # replaying an old token. Nuke the whole family.
        logger.warning("refresh_token_reuse_detected", family_id=str(stored.family_id), user_id=str(stored.user_id))
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == stored.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.commit()
        raise TokenReuseDetectedError("refresh token reuse detected; all sessions revoked")

    # Valid, unused token: rotate it.
    new_pair = await issue_token_pair(db, stored.user_id, family_id=stored.family_id)

    stored.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    return new_pair


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await db.commit()
