"""
FastAPI dependencies that every downstream service imports to protect routes.

Usage in any service:

    from shared_auth.dependencies import get_current_user_id, verifier_from_env

    verifier = verifier_from_env()

    @router.get("/repos")
    async def list_repos(user_id: str = Depends(get_current_user_id(verifier))):
        ...
"""
from __future__ import annotations

import os
from typing import Callable

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt_verifier import JWTVerifier, TokenError

_bearer_scheme = HTTPBearer(auto_error=False)


def verifier_from_env() -> JWTVerifier:
    """Every service loads the same public key via env var - set by k8s secret
    mount in production, or a local .env file in dev (matches the env_file
    behavior of each service's own pydantic Settings)."""
    load_dotenv()
    key_path = os.environ.get("JWT_PUBLIC_KEY_PATH", "/secrets/jwt/public.pem")
    issuer = os.environ.get("JWT_ISSUER", "auth-service")
    audience = os.environ.get("JWT_AUDIENCE", "code-review-platform")
    return JWTVerifier.from_key_file(key_path, issuer=issuer, audience=audience)


def get_current_user_id(verifier: JWTVerifier) -> Callable:
    """Returns a FastAPI dependency bound to a specific verifier instance."""

    async def _dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> str:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            claims = verifier.verify(credentials.credentials, expected_type="access")
        except TokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=exc.message,
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        return claims.subject

    return _dependency
