"""
Fetches exactly the commit a push webhook fired for, into a throwaway temp
dir, and reads back the changed files' contents - the "clone the code" step
in the pipeline. Deliberately narrow: this is not a general-purpose clone
helper, it exists only to hand file contents to the AI client.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import GitCloneError
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _run_git(args: list[str], cwd: Path, timeout: float) -> None:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise GitCloneError(f"git {args[0]} timed out after {timeout}s") from exc

    if proc.returncode != 0:
        # stderr may echo the remote URL (which embeds the token) on some git
        # versions' error output - truncate and never log it, only raise it
        # into an exception that's caught and logged as a generic failure.
        raise GitCloneError(f"git {args[0]} failed with exit code {proc.returncode}: {stderr.decode(errors='replace')[:500]}")


async def fetch_changed_files(
    repo_full_name: str,
    after_sha: str,
    changed_files: list[str],
    token: str,
) -> dict[str, str]:
    """
    Shallow-fetches exactly `after_sha` (GitHub allows fetching an arbitrary
    reachable commit SHA over HTTPS) into a throwaway temp dir, checks it
    out, and returns {path: content} for every path in `changed_files` that
    exists, is UTF-8 text, and is under the configured size cap. Binary,
    oversized, or missing files are silently skipped - there's nothing
    useful an LLM code review can say about a binary diff.

    `token` is a short-lived GitHub installation token (see
    installation_token_client) embedded only in the remote URL passed to
    git - never logged, never persisted.
    """
    settings = get_settings()
    tmp_dir = Path(tempfile.mkdtemp(prefix="ai-analysis-"))
    resolved_root = tmp_dir.resolve()
    auth_url = f"https://x-access-token:{token}@github.com/{repo_full_name}.git"

    try:
        await _run_git(["init", "-q"], cwd=tmp_dir, timeout=settings.clone_timeout_seconds)
        await _run_git(
            ["remote", "add", "origin", auth_url],
            cwd=tmp_dir,
            timeout=settings.clone_timeout_seconds,
        )
        await _run_git(
            ["fetch", "--depth", "1", "origin", after_sha],
            cwd=tmp_dir,
            timeout=settings.clone_timeout_seconds,
        )
        await _run_git(["checkout", "-q", "FETCH_HEAD"], cwd=tmp_dir, timeout=settings.clone_timeout_seconds)

        contents: dict[str, str] = {}
        for rel_path in changed_files[: settings.max_files_per_push]:
            file_path = (tmp_dir / rel_path).resolve()
            if not file_path.is_relative_to(resolved_root):
                # changed_files came from a webhook payload we trust, but
                # never let a path traversal ("../../etc/passwd") anywhere
                # near a filesystem read.
                logger.warning("file_skipped_path_traversal", path=rel_path)
                continue
            if not file_path.is_file():
                continue
            if file_path.stat().st_size > settings.max_file_bytes:
                logger.info("file_skipped_too_large", path=rel_path)
                continue
            try:
                contents[rel_path] = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                logger.info("file_skipped_binary", path=rel_path)
                continue

        return contents
    except GitCloneError:
        raise
    except Exception as exc:
        raise GitCloneError(f"unexpected error cloning {repo_full_name}@{after_sha}: {exc}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
