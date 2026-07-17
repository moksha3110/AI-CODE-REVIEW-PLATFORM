"""
Wraps the Claude API call that turns one changed file's content into a
structured code review - the "AI analyzes every changed file" step. Uses
structured outputs (`output_config.format`) instead of prompt-engineering
"reply with JSON" and hoping - the response is guaranteed to match
REVIEW_SCHEMA or the API itself rejects the request, so there's no
hand-rolled JSON-repair logic here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

from app.core.config import get_settings
from app.core.exceptions import AIProviderError
from app.core.logging import get_logger

logger = get_logger(__name__)

_ISSUE_ITEM = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "line": {"type": ["integer", "null"]},
    },
    "required": ["description", "severity", "line"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "1-3 sentence overview of the change in this file"},
        "complexity_score": {
            "type": "number",
            "description": "Complexity score from 1 (trivial) to 10 (very complex)",
        },
        "bugs": {"type": "array", "items": _ISSUE_ITEM},
        "security_issues": {"type": "array", "items": _ISSUE_ITEM},
        "optimizations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                },
                "required": ["description", "line"],
                "additionalProperties": False,
            },
        },
        "documentation_suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "complexity_score",
        "bugs",
        "security_issues",
        "optimizations",
        "documentation_suggestions",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are an automated code reviewer. You are given a single file's full "
    "content from a git push. Review it for bugs, security vulnerabilities, "
    "performance/optimization opportunities, and missing documentation. "
    "Estimate a complexity score from 1 (trivial) to 10 (very complex). "
    "Be specific and reference line numbers where you can determine them "
    "from the provided content. If you find nothing in a category, return "
    "an empty list for it - do not invent issues."
)


@dataclass(frozen=True)
class FileReview:
    file_path: str
    summary: str
    complexity_score: float
    bugs: list[dict]
    security_issues: list[dict]
    optimizations: list[dict]
    documentation_suggestions: list[str]


_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


async def review_file(file_path: str, content: str) -> FileReview:
    """
    Reviews one file's content. The Anthropic SDK already retries 429/5xx
    with backoff (default max_retries=2) - no extra retry wrapper needed
    here, only conversion of unretryable failures into AIProviderError.
    """
    settings = get_settings()
    client = _get_client()

    try:
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
            messages=[{"role": "user", "content": f"File: {file_path}\n\n```\n{content}\n```"}],
        )
    except anthropic.APIStatusError as exc:
        raise AIProviderError(f"claude review failed for {file_path}: status {exc.status_code}") from exc
    except anthropic.APIConnectionError as exc:
        raise AIProviderError(f"claude review connection failed for {file_path}") from exc

    if response.stop_reason == "refusal":
        raise AIProviderError(f"claude declined to review {file_path}")

    text_block = next((block for block in response.content if block.type == "text"), None)
    if text_block is None:
        raise AIProviderError(f"claude returned no text content for {file_path}")

    data = json.loads(text_block.text)
    return FileReview(
        file_path=file_path,
        summary=data["summary"],
        complexity_score=data["complexity_score"],
        bugs=data["bugs"],
        security_issues=data["security_issues"],
        optimizations=data["optimizations"],
        documentation_suggestions=data["documentation_suggestions"],
    )
