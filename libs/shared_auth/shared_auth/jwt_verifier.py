"""
Stateless JWT verification shared by every service in the platform.

Design decision: services do NOT call the Auth Service over the network to
validate a token on every request. Auth Service is the only holder of the
RSA private key and is the only signer. Every other service only needs the
public key to verify a signature locally - this removes Auth Service as a
single point of failure / latency bottleneck on the hot path of every
request across the whole platform.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import jwt
from jwt import PyJWTError

ALGORITHM = "RS256"


class TokenError(Exception):
    """Raised for any invalid, expired, or malformed token."""

    def __init__(self, message: str, code: str = "invalid_token"):
        self.message = message
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class TokenClaims:
    subject: str          # user id
    token_type: str       # "access" | "refresh"
    issued_at: int
    expires_at: int
    jti: str               # unique token id, used for refresh-token revocation lookups


class JWTVerifier:
    """Loads an RSA public key once and verifies bearer tokens against it."""

    def __init__(self, public_key: str, issuer: str = "auth-service", audience: str = "code-review-platform"):
        self._public_key = public_key
        self._issuer = issuer
        self._audience = audience

    @classmethod
    def from_key_file(cls, path: str | Path, **kwargs) -> "JWTVerifier":
        key_text = Path(path).read_text()
        return cls(public_key=key_text, **kwargs)

    def verify(self, token: str, expected_type: str = "access") -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "sub", "jti", "type"]},
            )
        except PyJWTError as exc:
            raise TokenError(f"token verification failed: {exc}") from exc

        if payload["type"] != expected_type:
            raise TokenError(
                f"expected token type '{expected_type}', got '{payload['type']}'",
                code="wrong_token_type",
            )

        return TokenClaims(
            subject=payload["sub"],
            token_type=payload["type"],
            issued_at=payload["iat"],
            expires_at=payload["exp"],
            jti=payload["jti"],
        )

    def is_expired(self, claims: TokenClaims) -> bool:
        return claims.expires_at < int(time.time())
