import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_path: str
    summary: str
    complexity_score: float
    bug_count: int
    security_issue_count: int
    optimization_count: int
    bugs: list[dict]
    security_issues: list[dict]
    optimizations: list[dict]
    documentation_suggestions: list[str]


class ReviewSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str
    ref: str
    after_sha: str
    overall_complexity_score: float
    total_bug_count: int
    total_security_issue_count: int
    analyzed_at: datetime


class ReviewDetailOut(ReviewSummaryOut):
    file_reviews: list[FileReviewOut]


class PaginatedReviewsOut(BaseModel):
    items: list[ReviewSummaryOut]
    total: int
    limit: int
    offset: int


class QualityTrendPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analyzed_at: datetime
    overall_complexity_score: float
    total_bug_count: int
    total_security_issue_count: int
