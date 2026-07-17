import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# shared_auth's verifier_from_env() needs SOME public key to load at import
# time - tests generate their own real keypair so they can mint tokens the
# verifier will actually accept, rather than overriding the dependency.
_tmp_dir = tempfile.mkdtemp()
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_private_path = Path(_tmp_dir) / "private.pem"
_public_path = Path(_tmp_dir) / "public.pem"
_private_path.write_bytes(
    _key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
)
_public_path.write_bytes(
    _key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
)

os.environ["JWT_PUBLIC_KEY_PATH"] = str(_public_path)
os.environ["JWT_ISSUER"] = "auth-service"
os.environ["JWT_AUDIENCE"] = "code-review-platform"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402


def _issue_access_token(subject: str = "11111111-1111-1111-1111-111111111111") -> str:
    import time

    import jwt

    now = int(time.time())
    payload = {
        "sub": subject,
        "type": "access",
        "iss": "auth-service",
        "aud": "code-review-platform",
        "iat": now,
        "exp": now + 900,
        "jti": "test-jti",
    }
    return jwt.encode(payload, _private_path.read_text(), algorithm="RS256")


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {_issue_access_token()}"}


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
