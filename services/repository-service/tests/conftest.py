import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# shared_auth's verifier_from_env() needs SOME public key to load at import
# time, even though these tests don't exercise auth-protected routes with
# real tokens - they override the dependency directly instead.
_tmp_dir = tempfile.mkdtemp()
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_path = Path(_tmp_dir) / "public.pem"
_public_path.write_bytes(
    _key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
)
os.environ["JWT_PUBLIC_KEY_PATH"] = str(_public_path)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["GITHUB_APP_ID"] = "test-app-id"
os.environ["GITHUB_WEBHOOK_SECRET"] = "test-webhook-secret"

from fakeredis.aioredis import FakeRedis  # noqa: E402

from app.api.deps import get_current_user_id_dep, get_redis  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_USER_ID = "11111111-1111-1111-1111-111111111111"


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


@pytest.fixture
def mock_publisher():
    """The real RabbitMQPublisher opens a network connection in .connect() -
    tests never want that, so main.py's lifespan is bypassed entirely by
    building the app directly rather than going through the ASGI lifespan
    context in these tests."""
    publisher = AsyncMock()
    return publisher


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
    app.dependency_overrides[get_current_user_id_dep] = lambda: TEST_USER_ID

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
