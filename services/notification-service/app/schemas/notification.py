import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str
    after_sha: str
    overall_complexity_score: float
    total_bug_count: int
    total_security_issue_count: int
    message: str
    read_at: datetime | None
    created_at: datetime


class PaginatedNotificationsOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int
    limit: int
    offset: int
