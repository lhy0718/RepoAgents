from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from repoagents.config.models import TrackerMode
from repoagents.logging import get_logger
from repoagents.models import ExternalActionResult, IssueComment, IssueRef
from repoagents.tracker.base import Tracker
from repoagents.tracker.issue_loader import load_issue_file
from repoagents.utils import ensure_dir, is_git_repository, run_git, sanitize_branch_name, sync_workspace_to_git_clone


class GitHubTracker(Tracker):
    def __init__(
        self,
        repo: str,
        api_url: str,
        token_env: str,
        repo_root: Path,
        mode: TrackerMode,
        fixtures_path: Path | None,
        allow_write_comments: bool,
        allow_open_pr: bool,
        dry_run: bool,
        max_retries: int = 3,
        base_retry_seconds: float = 1.0,
        rate_limit_warn_remaining: int = 10,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.repo = repo
        self.api_url = api_url.rstrip("/")
        self.token_env = token_env
        self.repo_root = repo_root
        self.mode = mode
        self.fixtures_path = fixtures_path
        self.allow_write_comments = allow_write_comments
        self.allow_open_pr = allow_open_pr
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.base_retry_seconds = base_retry_seconds
        self.rate_limit_warn_remaining = rate_limit_warn_remaining
        self.client = client or httpx.AsyncClient(timeout=20.0, follow_redirects=True)
        self.logger = get_logger("repoagents.tracker.github")

    async def list_open_issues(self) -> list[IssueRef]:
        if self.mode == TrackerMode.FIXTURE:
            return self._load_fixture_issues()

        issues = []
        next_ref: str | None = f"/repos/{self.repo}/issues"
        next_params: dict[str, Any] | None = {"state": "open", "per_page": 100, "page": 1}
        while next_ref:
            response = await self._request("GET", next_ref, params=next_params)
            for item in response.json():
                if "pull_request" in item:
                    continue
                issues.append(self._parse_issue(item))
            next_ref = self._extract_next_link(response.headers.get("Link"))
            next_params = None
        return issues

    async def get_issue(self, issue_id: int) -> IssueRef:
        if self.mode == TrackerMode.FIXTURE:
            for issue in self._load_fixture_issues():
                if issue.id == issue_id:
                    return issue
            raise KeyError(f"Issue {issue_id} not found in fixture file.")

        issue_response = await self._request("GET", f"/repos/{self.repo}/issues/{issue_id}")
        comments_response = await self._request(
            "GET",
            f"/repos/{self.repo}/issues/{issue_id}/comments",
            params={"per_page": 20},
        )
        issue = self._parse_issue(issue_response.json())
        issue.comments = [self._parse_comment(item) for item in comments_response.json()]
        return issue

    async def get_repo_info(self) -> dict[str, Any]:
        if self.mode == TrackerMode.FIXTURE:
            return {
                "full_name": self.repo,
                "default_branch": None,
                "private": None,
                "permissions": {},
            }
        response = await self._request("GET", f"/repos/{self.repo}")
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        return {}

    async def get_branch_info(self, branch: str) -> dict[str, Any]:
        if self.mode == TrackerMode.FIXTURE:
            return {
                "name": branch,
                "protected": False,
                "protection_url": None,
            }
        response = await self._request("GET", f"/repos/{self.repo}/branches/{branch}")
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        return {}

    async def get_branch_protection(self, branch: str) -> dict[str, Any]:
        if self.mode == TrackerMode.FIXTURE:
            return {}
        response = await self._request("GET", f"/repos/{self.repo}/branches/{branch}/protection")
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        return {}

    async def post_comment(self, issue_id: int, body: str) -> ExternalActionResult:
        if self.dry_run:
            return ExternalActionResult(
                action="post_comment",
                executed=False,
                reason="Dry-run mode blocks external writes.",
            )
        if not self.allow_write_comments:
            return ExternalActionResult(
                action="post_comment",
                executed=False,
                reason="safety.allow_write_comments=false",
            )
        if self.mode == TrackerMode.FIXTURE:
            return ExternalActionResult(
                action="post_comment",
                executed=False,
                reason="Fixture tracker is read-only.",
            )
        response = await self._request(
            "POST",
            f"/repos/{self.repo}/issues/{issue_id}/comments",
            json={"body": body},
        )
        return ExternalActionResult(
            action="post_comment",
            executed=True,
            reason="Comment posted to GitHub issue.",
            payload={
                "url": response.json().get("html_url"),
                "comment_id": response.json().get("id"),
            },
        )

    async def create_branch(
        self,
        issue_id: int,
        name: str,
        workspace_path: Path,
        commit_message: str,
    ) -> ExternalActionResult:
        if self.dry_run:
            return ExternalActionResult(
                action="create_branch",
                executed=False,
                reason="Dry-run mode blocks branch creation.",
                payload={"issue_id": issue_id, "requested_name": name},
            )
        if not self.allow_open_pr:
            return ExternalActionResult(
                action="create_branch",
                executed=False,
                reason="safety.allow_open_pr=false",
                payload={"issue_id": issue_id, "requested_name": name},
            )
        if self.mode == TrackerMode.FIXTURE:
            return ExternalActionResult(
                action="create_branch",
                executed=False,
                reason="Fixture tracker is read-only.",
                payload={"issue_id": issue_id, "requested_name": name},
            )
        if not is_git_repository(self.repo_root):
            raise RuntimeError(f"Repo root is not a git repository: {self.repo_root}")

        branch_name = sanitize_branch_name(name, issue_id=issue_id)
        stage_root = (
            self.repo_root
            / ".ai-repoagents"
            / "branches"
            / f"issue-{issue_id}"
            / branch_name.replace("/", "__")
        )
        if stage_root.exists():
            shutil.rmtree(stage_root)
        ensure_dir(stage_root.parent)

        origin_url = run_git(["remote", "get-url", "origin"], self.repo_root)
        repo_info = await self.get_repo_info()
        local_branch = run_git(["branch", "--show-current"], self.repo_root)
        base_branch = str(repo_info.get("default_branch") or "").strip() or local_branch or "main"

        run_git(["clone", "--local", str(self.repo_root), str(stage_root)], self.repo_root)
        run_git(["remote", "set-url", "origin", origin_url], stage_root)
        run_git(["fetch", "origin", base_branch], stage_root)
        run_git(["checkout", "-B", branch_name, f"origin/{base_branch}"], stage_root)
        sync_workspace_to_git_clone(workspace_path, stage_root)
        run_git(["add", "-A"], stage_root)

        if not run_git(["status", "--short"], stage_root):
            return ExternalActionResult(
                action="create_branch",
                executed=False,
                reason="No workspace changes to publish.",
                payload={
                    "issue_id": issue_id,
                    "branch_name": branch_name,
                    "base_branch": base_branch,
                    "local_branch": local_branch or None,
                    "stage_path": str(stage_root),
                },
            )

        run_git(
            [
                "-c",
                "user.name=RepoAgents Bot",
                "-c",
                "user.email=repoagents@example.invalid",
                "commit",
                "-m",
                commit_message,
            ],
            stage_root,
        )
        run_git(["push", "-u", "origin", branch_name], stage_root)
        return ExternalActionResult(
            action="create_branch",
            executed=True,
            reason="Created and pushed branch to origin.",
            payload={
                "issue_id": issue_id,
                "branch_name": branch_name,
                "base_branch": base_branch,
                "local_branch": local_branch or None,
                "origin_url": _redact_remote_url(origin_url),
                "stage_path": str(stage_root),
            },
        )

    async def open_pr(
        self,
        issue_id: int,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        draft: bool = True,
    ) -> ExternalActionResult:
        if self.dry_run:
            return ExternalActionResult(
                action="open_pr",
                executed=False,
                reason="Dry-run mode blocks external writes.",
            )
        if not self.allow_open_pr:
            return ExternalActionResult(
                action="open_pr",
                executed=False,
                reason="safety.allow_open_pr=false",
            )
        if self.mode == TrackerMode.FIXTURE:
            return ExternalActionResult(
                action="open_pr",
                executed=False,
                reason="Fixture tracker is read-only.",
            )
        response = await self._request(
            "POST",
            f"/repos/{self.repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
                "draft": draft,
            },
        )
        payload = response.json()
        return ExternalActionResult(
            action="open_pr",
            executed=True,
            reason="Opened draft pull request on GitHub.",
            payload={
                "issue_id": issue_id,
                "title": title,
                "url": payload.get("html_url"),
                "number": payload.get("number"),
                "head_branch": head_branch,
                "base_branch": base_branch,
                "draft": payload.get("draft", draft),
            },
        )

    async def set_issue_label(self, issue_id: int, labels: list[str]) -> ExternalActionResult:
        if self.dry_run:
            return ExternalActionResult(
                action="set_issue_label",
                executed=False,
                reason="Dry-run mode blocks external writes.",
            )
        if self.mode == TrackerMode.FIXTURE:
            return ExternalActionResult(
                action="set_issue_label",
                executed=False,
                reason="Fixture tracker is read-only.",
            )
        response = await self._request(
            "POST",
            f"/repos/{self.repo}/issues/{issue_id}/labels",
            json={"labels": labels},
        )
        return ExternalActionResult(
            action="set_issue_label",
            executed=True,
            reason="Labels updated on GitHub issue.",
            payload={"labels": response.json()},
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        method = method.upper()
        headers = kwargs.pop("headers", {})
        token = os.getenv(self.token_env)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
        url = path if path.startswith(("http://", "https://")) else f"{self.api_url}{path}"
        retryable = method in {"GET", "HEAD", "OPTIONS"}
        max_attempts = self.max_retries + 1 if retryable else 1

        for attempt in range(1, max_attempts + 1):
            try:
                response = await self.client.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs,
                )
            except httpx.TransportError as exc:
                if attempt >= max_attempts:
                    raise
                delay = self._compute_retry_delay(attempt=attempt)
                self.logger.warning(
                    "GitHub API transport error; retrying",
                    extra={
                        "repo": self.repo,
                        "method": method,
                        "url": url,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "delay_seconds": delay,
                        "error": str(exc),
                    },
                )
                await self._sleep(delay)
                continue

            self._log_rate_limit_status(method, url, response)
            if retryable and self._should_retry_response(response) and attempt < max_attempts:
                delay = self._compute_retry_delay(attempt=attempt, response=response)
                self.logger.warning(
                    "GitHub API retry scheduled",
                    extra={
                        "repo": self.repo,
                        "method": method,
                        "url": url,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "status_code": response.status_code,
                        "delay_seconds": delay,
                    },
                )
                await self._sleep(delay)
                continue

            response.raise_for_status()
            return response

        raise RuntimeError(f"Exhausted retry loop for {method} {url}")

    def _load_fixture_issues(self) -> list[IssueRef]:
        if not self.fixtures_path:
            raise FileNotFoundError("Fixture mode requires a fixture issue file.")
        path = self.fixtures_path
        if not path.is_absolute():
            path = (self.repo_root / path).resolve()
        return load_issue_file(path)

    def _parse_issue(self, payload: dict[str, Any]) -> IssueRef:
        return IssueRef.model_validate(
            {
                "id": payload["number"],
                "number": payload["number"],
                "title": payload["title"],
                "body": payload.get("body") or "",
                "labels": [label["name"] for label in payload.get("labels", [])],
                "comments": [],
                "url": payload.get("html_url"),
                "updated_at": payload.get("updated_at"),
            }
        )

    def _parse_comment(self, payload: dict[str, Any]) -> IssueComment:
        return IssueComment.model_validate(
            {
                "author": (payload.get("user") or {}).get("login", "unknown"),
                "body": payload.get("body") or "",
                "created_at": payload.get("created_at"),
            }
        )

    def _should_retry_response(self, response: httpx.Response) -> bool:
        if response.status_code >= 500:
            return True
        if response.status_code == 429:
            return True
        if response.status_code == 403 and self._is_rate_limited(response):
            return True
        return False

    def _is_rate_limited(self, response: httpx.Response) -> bool:
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining == "0":
            return True
        if response.status_code == 429:
            return True
        if response.headers.get("Retry-After") and response.status_code == 403:
            return True
        if response.status_code != 403:
            return False
        body = response.text.lower()
        return "rate limit" in body

    def _compute_retry_delay(
        self,
        attempt: int,
        response: httpx.Response | None = None,
    ) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(0.0, float(retry_after))
                except ValueError:
                    pass
            reset_at = response.headers.get("X-RateLimit-Reset")
            if reset_at:
                try:
                    return max(0.0, float(reset_at) - time.time())
                except ValueError:
                    pass
        return min(self.base_retry_seconds * (2 ** (attempt - 1)), 30.0)

    def _extract_next_link(self, link_header: str | None) -> str | None:
        if not link_header:
            return None
        for part in link_header.split(","):
            section = part.strip()
            if 'rel="next"' not in section:
                continue
            url_part = section.split(";", 1)[0].strip()
            if url_part.startswith("<") and url_part.endswith(">"):
                return url_part[1:-1]
        return None

    def _log_rate_limit_status(self, method: str, url: str, response: httpx.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        limit = response.headers.get("X-RateLimit-Limit")
        reset_at = response.headers.get("X-RateLimit-Reset")
        if remaining is None:
            return
        try:
            remaining_count = int(remaining)
        except ValueError:
            return
        if remaining_count > self.rate_limit_warn_remaining:
            return
        self.logger.warning(
            "GitHub API rate limit is low",
            extra={
                "repo": self.repo,
                "method": method,
                "url": url,
                "status_code": response.status_code,
                "rate_limit_remaining": remaining_count,
                "rate_limit_limit": int(limit) if limit and limit.isdigit() else limit,
                "rate_limit_reset": reset_at,
            },
        )

    async def _sleep(self, delay_seconds: float) -> None:
        await asyncio.sleep(delay_seconds)


def _redact_remote_url(remote_url: str) -> str:
    try:
        parsed = urlsplit(remote_url)
    except ValueError:
        return remote_url
    if not parsed.scheme or "@" not in parsed.netloc:
        return remote_url
    hostname = parsed.hostname or ""
    if parsed.port is not None:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path, parsed.query, parsed.fragment))
