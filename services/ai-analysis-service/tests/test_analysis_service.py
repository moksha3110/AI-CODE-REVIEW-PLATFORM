import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.core.exceptions import GitCloneError
from app.models.analysis_run import AnalysisRun
from app.models.outbox_event import OutboxEvent
from app.services import analysis_service, git_service, installation_token_client
from app.services.ai_client import FileReview

pytestmark = pytest.mark.asyncio


def _payload(**overrides) -> dict:
    base = {
        "push_event_id": str(uuid.uuid4()),
        "repository_id": str(uuid.uuid4()),
        "repository_full_name": "octo/hello-world",
        "installation_id": str(uuid.uuid4()),
        "github_installation_id": 12345,
        "ref": "refs/heads/main",
        "before_sha": "b" * 40,
        "after_sha": "a" * 40,
        "changed_files": ["main.py", "new_file.py"],
    }
    base.update(overrides)
    return base


def _fake_review(file_path: str) -> FileReview:
    return FileReview(
        file_path=file_path,
        summary="Looks fine.",
        complexity_score=3.5,
        bugs=[],
        security_issues=[],
        optimizations=[],
        documentation_suggestions=[],
    )


async def test_process_analysis_request_happy_path(db_session, monkeypatch):
    monkeypatch.setattr(installation_token_client, "get_installation_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(
        git_service,
        "fetch_changed_files",
        AsyncMock(return_value={"main.py": "print(1)", "new_file.py": "print(2)"}),
    )
    review_mock = AsyncMock(side_effect=lambda file_path, content: _fake_review(file_path))
    monkeypatch.setattr(analysis_service.ai_client, "review_file", review_mock)

    payload = _payload()
    await analysis_service.process_analysis_request(db_session, payload)

    run_result = await db_session.execute(
        select(AnalysisRun).where(AnalysisRun.push_event_id == uuid.UUID(payload["push_event_id"]))
    )
    run = run_result.scalar_one()
    assert run.status == "completed"
    assert run.attempts == 1
    assert run.error_message is None

    outbox_result = await db_session.execute(select(OutboxEvent).where(OutboxEvent.aggregate_id == run.id))
    outbox_row = outbox_result.scalar_one()
    assert outbox_row.routing_key == "review.completed"
    assert outbox_row.published_at is None
    assert outbox_row.payload["repository_full_name"] == "octo/hello-world"
    assert len(outbox_row.payload["file_reviews"]) == 2
    assert outbox_row.payload["overall_complexity_score"] == 3.5
    assert review_mock.await_count == 2


async def test_duplicate_push_event_is_processed_once(db_session, monkeypatch):
    monkeypatch.setattr(installation_token_client, "get_installation_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(git_service, "fetch_changed_files", AsyncMock(return_value={"main.py": "print(1)"}))
    review_mock = AsyncMock(side_effect=lambda file_path, content: _fake_review(file_path))
    monkeypatch.setattr(analysis_service.ai_client, "review_file", review_mock)

    payload = _payload()
    await analysis_service.process_analysis_request(db_session, payload)
    await analysis_service.process_analysis_request(db_session, payload)

    outbox_result = await db_session.execute(select(OutboxEvent))
    assert len(outbox_result.scalars().all()) == 1
    assert review_mock.await_count == 1  # second call was skipped entirely


async def test_failed_analysis_marks_run_failed_and_reraises(db_session, monkeypatch):
    monkeypatch.setattr(installation_token_client, "get_installation_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(
        git_service, "fetch_changed_files", AsyncMock(side_effect=GitCloneError("clone blew up"))
    )

    payload = _payload()
    with pytest.raises(GitCloneError):
        await analysis_service.process_analysis_request(db_session, payload)

    run_result = await db_session.execute(
        select(AnalysisRun).where(AnalysisRun.push_event_id == uuid.UUID(payload["push_event_id"]))
    )
    run = run_result.scalar_one()
    assert run.status == "failed"
    assert "clone blew up" in run.error_message

    outbox_result = await db_session.execute(select(OutboxEvent))
    assert outbox_result.scalars().all() == []


async def test_failed_run_is_retried_until_attempt_budget_exhausted(db_session, monkeypatch):
    monkeypatch.setattr(installation_token_client, "get_installation_token", AsyncMock(return_value="tok"))
    monkeypatch.setattr(
        git_service, "fetch_changed_files", AsyncMock(side_effect=GitCloneError("still broken"))
    )

    payload = _payload()
    for _ in range(3):  # matches default MAX_ANALYSIS_ATTEMPTS
        with pytest.raises(GitCloneError):
            await analysis_service.process_analysis_request(db_session, payload)

    run_result = await db_session.execute(
        select(AnalysisRun).where(AnalysisRun.push_event_id == uuid.UUID(payload["push_event_id"]))
    )
    run = run_result.scalar_one()
    assert run.attempts == 3

    # Retry budget exhausted - a 4th claim attempt is skipped without even
    # calling the pipeline again.
    fetch_mock = git_service.fetch_changed_files
    await analysis_service.process_analysis_request(db_session, payload)
    assert fetch_mock.await_count == 3
