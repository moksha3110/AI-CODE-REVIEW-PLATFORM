"""
Token signing lives ONLY here. Auth Service holds the RSA private key;
every other service (via libs/shared_auth) only ever sees the public key.

Access tokens: short-lived (15 min default), stateless, carry no server-side
lookup on the hot path.

Refresh tokens: longer-lived (7 day default), tracked server-side in the
`refresh_tokens` table so they can be individually revoked. Each refresh
issues a NEW refresh token and invalidates the old one (rotation). If a
refresh token is presented a second time after being rotated, that's a signal
of theft/replay -> we revoke the entire token family, not just the one token.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import jwt

from app.core.config import get_settings

ALGORITHM = "RS256"


@lru_cache
def _load_private_key() -> str:
    settings = get_settings()
    return Path(settings.jwt_private_key_path).read_text()


@lru_cache
def _load_public_key() -> str:
    settings = get_settings()
    return Path(settings.jwt_public_key_path).read_text()


@dataclass(frozen=True)
class IssuedToken:
    token: str
    jti: str
    expires_at: int


def _sign(subject: str, token_type: str, ttl_seconds: int) -> IssuedToken:
    settings = get_settings()
    now = int(time.time())
    jti = str(uuid.uuid4())
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": jti,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(payload, _load_private_key(), algorithm=ALGORITHM)
    return IssuedToken(token=token, jti=jti, expires_at=payload["exp"])


def issue_access_token(user_id: str) -> IssuedToken:
    settings = get_settings()
    return _sign(user_id, "access", settings.access_token_expire_minutes * 60)


def issue_refresh_token(user_id: str) -> IssuedToken:
    settings = get_settings()
    return _sign(user_id, "refresh", settings.refresh_token_expire_days * 86400)


def decode_token(token: str, expected_type: str) -> dict:
    """Raises jwt.PyJWTError subclasses on any invalid/expired/tampered token."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        _load_public_key(),
        algorithms=[ALGORITHM],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        options={"require": ["exp", "iat", "sub", "jti", "type"]},
    )
    if payload["type"] != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token, got {payload['type']}")
    return payload
