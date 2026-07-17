import uuid

import pytest

from app.models.installation import Installation
from app.models.repository import Repository

pytestmark = pytest.mark.asyncio

INTERNAL_HEADERS = {"X-Internal-Api-Key": "change_me_internal_key"}


async def _seed_repository(db_session, connected_by_user_id: uuid.UUID) -> Repository:
    installation = Installation(
        id=uuid.uuid4(),
        github_installation_id=12345,
        account_login="octo",
        account_type="Organization",
        connected_by_user_id=connected_by_user_id,
    )
    repo = Repository(
        id=uuid.uuid4(),
        installation_id=installation.id,
        github_repo_id=999,
        full_name="octo/hello-world",
        default_branch="main",
        is_private=True,
    )
    db_session.add(installation)
    db_session.add(repo)
    await db_session.commit()
    return repo


async def test_get_repository_owner_requires_internal_key(client, db_session):
    repo = await _seed_repository(db_session, connected_by_user_id=uuid.uuid4())
    resp = await client.get(f"/api/v1/internal/repositories/{repo.id}/owner")
    assert resp.status_code == 401


async def test_get_repository_owner_returns_connected_user(client, db_session):
    owner_id = uuid.uuid4()
    repo = await _seed_repository(db_session, connected_by_user_id=owner_id)

    resp = await client.get(f"/api/v1/internal/repositories/{repo.id}/owner", headers=INTERNAL_HEADERS)

    assert resp.status_code == 200
    assert resp.json()["user_id"] == str(owner_id)


async def test_get_repository_owner_404_for_unknown_repository(client):
    resp = await client.get(f"/api/v1/internal/repositories/{uuid.uuid4()}/owner", headers=INTERNAL_HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "repository_not_found"
