# Auth service

Handles GitHub OAuth login for platform users and issues/verifies the
platform's own JWTs (RS256). Every other service trusts this service's
public key to verify tokens locally - no network call to Auth Service on
the hot path.

## What's implemented

- **GitHub OAuth login** (`GET /api/v1/auth/github/login` ->
  `GET /api/v1/auth/github/callback`) - CSRF-protected via a
  Redis-backed `state` parameter, rate-limited per IP.
- **JWT issuance (RS256)** - short-lived access tokens (15 min default)
  handed back to the browser as a URL fragment (never a query param, so
  it's never sent to a server or logged), plus a long-lived refresh token
  set as an httpOnly cookie.
- **Refresh-token rotation with reuse detection** - every `/refresh` call
  issues a new token and revokes the old one; if a revoked token is ever
  presented again (a theft signal), the entire token family is revoked,
  not just the one token. See `app/services/token_service.py`.
- **Stateless verification everywhere else** - `libs/shared_auth` (used by
  every other service) verifies tokens using only this service's public
  key, mounted read-only. Only this service holds the private key.
- `GET /api/v1/auth/me` - returns the authenticated user's profile.
- `POST /api/v1/auth/logout` - revokes the refresh token family and clears
  the cookie.

## Running locally

```bash
./scripts/generate_keys.sh   # RSA keypair this service signs JWTs with -
                              # the public half gets mounted read-only into
                              # every other service
cp .env.example .env
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Swagger docs: http://localhost:8000/docs

## Known gaps / honest trade-offs

- **`rotate_refresh_token` isn't fully atomic.** It issues the new token
  pair and revokes the old one in two separate commits on the same
  session, not one transaction. Low risk (same session, sequential
  awaits), but the correct fix is wrapping both in an explicit
  `async with db.begin():` block.
- **No roles or permissions.** Every authenticated user has full access to
  their own data; there's no admin/member distinction anywhere in the
  platform.
- **Login rate limiting is per-IP, not per-account** - fine for this
  project's scale, would want per-account limiting too at real scale to
  resist distributed credential-stuffing.
