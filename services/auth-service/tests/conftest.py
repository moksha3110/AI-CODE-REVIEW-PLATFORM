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

# Generate a throwaway RSA keypair and point the app at it BEFORE importing
# any app module, since config/security load key paths at import time.
_tmp_dir = tempfile.mkdtemp()
_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_private_path = Path(_tmp_dir) / "private.pem"
_public_path = Path(_tmp_dir) / "public.pem"
_private_path.write_bytes(
    _private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
)
_public_path.write_bytes(
    _private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
)

os.environ["JWT_PRIVATE_KEY_PATH"] = str(_private_path)
os.environ["JWT_PUBLIC_KEY_PATH"] = str(_public_path)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["GITHUB_CLIENT_ID"] = "test-client-id"
os.environ["GITHUB_CLIENT_SECRET"] = "test-client-secret"

from fakeredis.aioredis import FakeRedis  # noqa: E402

from app.api.deps import get_redis  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402


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

    fake_redis = FakeRedis(decode_responses=True)

    async def _override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = _override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def rsa_key_paths():
    return _private_path, _public_path
