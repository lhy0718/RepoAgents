from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

from reporepublic.config.models import TrackerMode
from reporepublic.tracker import build_tracker
from reporepublic.tracker.github import GitHubTracker, _redact_remote_url
from reporepublic.tracker.local_file import LocalFileTracker
from reporepublic.tracker.local_markdown import LocalMarkdownTracker
from reporepublic.config import load_config


def test_github_tracker_create_branch_and_open_pr(tmp_path: Path) -> None:
    remote_repo = tmp_path / "remote.git"
    source_repo = tmp_path / "source"
    workspace = tmp_path / "workspace"

    subprocess.run(
        ["git", "init", "--bare", str(remote_repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    source_repo.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "init", "-b", "main"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
        text=True,
    )
    (source_repo / "README.md").write_text("# Demo Repo\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source_repo), "add", "-A"], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "remote", "add", "origin", str(remote_repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "push", "-u", "origin", "main"],
        check=True,
        capture_output=True,
        text=True,
    )

    shutil.copytree(source_repo, workspace, ignore=shutil.ignore_patterns(".git"))
    (workspace / "README.md").write_text(
        "# Demo Repo\n\n## Quickstart\n\n1. Install.\n",
        encoding="utf-8",
    )

    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and str(request.url).endswith("/repos/demo/repo"):
            return httpx.Response(
                200,
                json={
                    "full_name": "demo/repo",
                    "default_branch": "main",
                    "private": False,
                    "permissions": {"pull": True, "push": True},
                },
            )
        requests.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            201,
            json={
                "html_url": "https://github.example/demo/repo/pull/1",
                "number": 1,
                "draft": True,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tracker = GitHubTracker(
        repo="demo/repo",
        api_url="https://api.github.com",
        token_env="GITHUB_TOKEN",
        repo_root=source_repo,
        mode=TrackerMode.REST,
        fixtures_path=None,
        allow_write_comments=True,
        allow_open_pr=True,
        dry_run=False,
        client=client,
    )

    async def run_flow():
        branch_result = await tracker.create_branch(
            issue_id=7,
            name="RepoRepublic/Issue 7 Improve README!!!",
            workspace_path=workspace,
            commit_message="republic: address issue #7",
        )
        pr_result = await tracker.open_pr(
            issue_id=7,
            title="RepoRepublic: Improve README (#7)",
            body="Body",
            head_branch=branch_result.payload["branch_name"],
            base_branch=branch_result.payload["base_branch"],
            draft=True,
        )
        await tracker.aclose()
        return branch_result, pr_result

    branch_result, pr_result = asyncio.run(run_flow())
    assert branch_result.executed is True
    assert branch_result.payload["branch_name"].startswith("reporepublic/")
    assert branch_result.payload["base_branch"] == "main"
    assert pr_result.executed is True
    assert pr_result.payload["url"] == "https://github.example/demo/repo/pull/1"
    assert requests[0]["head"] == branch_result.payload["branch_name"]
    assert requests[0]["base"] == "main"
    refs = subprocess.run(
        [
            "git",
            f"--git-dir={remote_repo}",
            "show-ref",
            f"refs/heads/{branch_result.payload['branch_name']}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert refs.returncode == 0


def test_github_tracker_blocks_branch_creation_in_dry_run(tmp_path: Path) -> None:
    tracker = GitHubTracker(
        repo="demo/repo",
        api_url="https://api.github.com",
        token_env="GITHUB_TOKEN",
        repo_root=tmp_path,
        mode=TrackerMode.REST,
        fixtures_path=None,
        allow_write_comments=True,
        allow_open_pr=True,
        dry_run=True,
    )
    result = asyncio.run(
        tracker.create_branch(
            issue_id=1,
            name="reporepublic/issue-1-test",
            workspace_path=tmp_path,
            commit_message="test",
        )
    )
    assert result.executed is False
    assert "Dry-run" in result.reason


def test_github_tracker_get_repo_info() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/repos/demo/repo")
        return httpx.Response(
            200,
            json={
                "full_name": "demo/repo",
                "default_branch": "main",
                "private": False,
                "permissions": {"pull": True, "push": False},
            },
        )

    tracker = GitHubTracker(
        repo="demo/repo",
        api_url="https://api.github.com",
        token_env="GITHUB_TOKEN",
        repo_root=Path.cwd(),
        mode=TrackerMode.REST,
        fixtures_path=None,
        allow_write_comments=True,
        allow_open_pr=True,
        dry_run=False,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def run_flow():
        payload = await tracker.get_repo_info()
        await tracker.aclose()
        return payload

    payload = asyncio.run(run_flow())
    assert payload["full_name"] == "demo/repo"
    assert payload["default_branch"] == "main"


def test_github_tracker_get_branch_info_and_protection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/repos/demo/repo/branches/main/protection"):
            return httpx.Response(
                200,
                json={
                    "required_pull_request_reviews": {"required_approving_review_count": 1},
                    "required_status_checks": {"strict": True, "contexts": ["pytest"]},
                    "enforce_admins": {"enabled": True},
                },
            )
        assert str(request.url).endswith("/repos/demo/repo/branches/main")
        return httpx.Response(
            200,
            json={
                "name": "main",
                "protected": True,
                "protection_url": "https://api.github.com/repos/demo/repo/branches/main/protection",
            },
        )

    tracker = GitHubTracker(
        repo="demo/repo",
        api_url="https://api.github.com",
        token_env="GITHUB_TOKEN",
        repo_root=Path.cwd(),
        mode=TrackerMode.REST,
        fixtures_path=None,
        allow_write_comments=True,
        allow_open_pr=True,
        dry_run=False,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def run_flow():
        branch = await tracker.get_branch_info("main")
        protection = await tracker.get_branch_protection("main")
        await tracker.aclose()
        return branch, protection

    branch, protection = asyncio.run(run_flow())
    assert branch["protected"] is True
    assert protection["required_pull_request_reviews"]["required_approving_review_count"] == 1
    assert protection["required_status_checks"]["contexts"] == ["pytest"]


def test_github_tracker_create_branch_prefers_repo_default_branch_over_local_head(tmp_path: Path) -> None:
    remote_repo = tmp_path / "remote.git"
    source_repo = tmp_path / "source"
    workspace = tmp_path / "workspace"

    subprocess.run(
        ["git", "init", "--bare", str(remote_repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    source_repo.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "init", "-b", "main"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
        text=True,
    )
    (source_repo / "README.md").write_text("# Demo Repo\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source_repo), "add", "-A"], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "remote", "add", "origin", str(remote_repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "push", "-u", "origin", "main"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "checkout", "-b", "feature/local-only"],
        check=True,
        capture_output=True,
        text=True,
    )
    (source_repo / "LOCAL.txt").write_text("feature branch only\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source_repo), "add", "-A"], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "commit", "-m", "feature work"],
        check=True,
        capture_output=True,
        text=True,
    )

    shutil.copytree(source_repo, workspace, ignore=shutil.ignore_patterns(".git"))
    (workspace / "README.md").write_text("# Demo Repo\n\nUpdated\n", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and str(request.url).endswith("/repos/demo/repo"):
            return httpx.Response(
                200,
                json={
                    "full_name": "demo/repo",
                    "default_branch": "main",
                    "private": False,
                    "permissions": {"pull": True, "push": True},
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    tracker = GitHubTracker(
        repo="demo/repo",
        api_url="https://api.github.com",
        token_env="GITHUB_TOKEN",
        repo_root=source_repo,
        mode=TrackerMode.REST,
        fixtures_path=None,
        allow_write_comments=True,
        allow_open_pr=True,
        dry_run=False,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def run_flow():
        result = await tracker.create_branch(
            issue_id=9,
            name="codex/default-branch-policy",
            workspace_path=workspace,
            commit_message="republic: test default branch policy",
        )
        await tracker.aclose()
        return result

    result = asyncio.run(run_flow())
    assert result.executed is True
    assert result.payload["base_branch"] == "main"
    assert result.payload["local_branch"] == "feature/local-only"


def test_github_tracker_list_open_issues_paginates() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        page = request.url.params.get("page", "1")
        if page == "1":
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 1,
                        "title": "Issue one",
                        "body": "Body",
                        "labels": [{"name": "bug"}],
                        "html_url": "https://github.example/1",
                    },
                    {
                        "number": 99,
                        "title": "PR shadow",
                        "body": "Should be filtered",
                        "labels": [],
                        "html_url": "https://github.example/pr/99",
                        "pull_request": {"url": "https://github.example/pr/99"},
                    },
                ],
                headers={
                    "Link": '<https://api.github.com/repos/demo/repo/issues?state=open&per_page=100&page=2>; rel="next"',
                    "X-RateLimit-Remaining": "99",
                    "X-RateLimit-Limit": "5000",
                },
            )
        return httpx.Response(
            200,
            json=[
                {
                    "number": 2,
                    "title": "Issue two",
                    "body": "Body",
                    "labels": [{"name": "docs"}],
                    "html_url": "https://github.example/2",
                }
            ],
            headers={
                "X-RateLimit-Remaining": "98",
                "X-RateLimit-Limit": "5000",
            },
        )

    tracker = GitHubTracker(
        repo="demo/repo",
        api_url="https://api.github.com",
        token_env="GITHUB_TOKEN",
        repo_root=Path.cwd(),
        mode=TrackerMode.REST,
        fixtures_path=None,
        allow_write_comments=True,
        allow_open_pr=True,
        dry_run=False,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def run_flow():
        issues = await tracker.list_open_issues()
        await tracker.aclose()
        return issues

    issues = asyncio.run(run_flow())
    assert [issue.id for issue in issues] == [1, 2]
    assert any("page=2" in request for request in requests)


def test_github_tracker_retries_rate_limited_requests() -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []
    log_messages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                429,
                json={"message": "API rate limit exceeded"},
                headers={
                    "Retry-After": "0",
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Limit": "5000",
                    "X-RateLimit-Reset": "9999999999",
                },
            )
        return httpx.Response(
            200,
            json=[
                {
                    "number": 1,
                    "title": "Recovered issue",
                    "body": "",
                    "labels": [],
                    "html_url": "https://github.example/1",
                }
            ],
            headers={
                "X-RateLimit-Remaining": "9",
                "X-RateLimit-Limit": "5000",
            },
        )

    tracker = GitHubTracker(
        repo="demo/repo",
        api_url="https://api.github.com",
        token_env="GITHUB_TOKEN",
        repo_root=Path.cwd(),
        mode=TrackerMode.REST,
        fixtures_path=None,
        allow_write_comments=True,
        allow_open_pr=True,
        dry_run=False,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def fake_sleep(delay_seconds: float) -> None:
        sleeps.append(delay_seconds)

    tracker._sleep = fake_sleep  # type: ignore[method-assign]
    tracker.logger = _SpyLogger(log_messages)

    async def run_flow():
        issues = await tracker.list_open_issues()
        await tracker.aclose()
        return issues

    issues = asyncio.run(run_flow())
    assert [issue.id for issue in issues] == [1]
    assert attempts["count"] == 2
    assert sleeps == [0.0]
    assert any("GitHub API retry scheduled" in message for message in log_messages)
    assert any("GitHub API rate limit is low" in message for message in log_messages)


def test_github_tracker_retries_server_errors_then_recovers() -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []
    log_messages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(
                503,
                json={"message": "temporary outage"},
                headers={
                    "X-RateLimit-Remaining": "50",
                    "X-RateLimit-Limit": "5000",
                },
                request=request,
            )
        return httpx.Response(
            200,
            json=[
                {
                    "number": 11,
                    "title": "Recovered issue",
                    "body": "",
                    "labels": [],
                    "html_url": "https://github.example/11",
                }
            ],
            headers={
                "X-RateLimit-Remaining": "49",
                "X-RateLimit-Limit": "5000",
            },
            request=request,
        )

    tracker = GitHubTracker(
        repo="demo/repo",
        api_url="https://api.github.com",
        token_env="GITHUB_TOKEN",
        repo_root=Path.cwd(),
        mode=TrackerMode.REST,
        fixtures_path=None,
        allow_write_comments=True,
        allow_open_pr=True,
        dry_run=False,
        max_retries=3,
        base_retry_seconds=0.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def fake_sleep(delay_seconds: float) -> None:
        sleeps.append(delay_seconds)

    tracker._sleep = fake_sleep  # type: ignore[method-assign]
    tracker.logger = _SpyLogger(log_messages)

    async def run_flow():
        issues = await tracker.list_open_issues()
        await tracker.aclose()
        return issues

    issues = asyncio.run(run_flow())
    assert [issue.id for issue in issues] == [11]
    assert attempts["count"] == 3
    assert sleeps == [0.0, 0.0]
    assert any("GitHub API retry scheduled" in message for message in log_messages)


def test_github_tracker_raises_after_retry_exhaustion_on_server_error() -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            503,
            json={"message": "still failing"},
            headers={
                "X-RateLimit-Remaining": "50",
                "X-RateLimit-Limit": "5000",
            },
            request=request,
        )

    tracker = GitHubTracker(
        repo="demo/repo",
        api_url="https://api.github.com",
        token_env="GITHUB_TOKEN",
        repo_root=Path.cwd(),
        mode=TrackerMode.REST,
        fixtures_path=None,
        allow_write_comments=True,
        allow_open_pr=True,
        dry_run=False,
        max_retries=2,
        base_retry_seconds=0.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    async def fake_sleep(delay_seconds: float) -> None:
        sleeps.append(delay_seconds)

    tracker._sleep = fake_sleep  # type: ignore[method-assign]

    async def run_flow():
        try:
            await tracker.list_open_issues()
        finally:
            await tracker.aclose()

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(run_flow())

    assert attempts["count"] == 3
    assert sleeps == [0.0, 0.0]


def test_local_file_tracker_reads_issue_file_and_stages_sync_actions(tmp_path: Path) -> None:
    issue_file = tmp_path / "issues.json"
    issue_file.write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "number": 1,
                    "title": "Fix empty input crash",
                    "body": "Return an empty list.",
                    "labels": ["bug"],
                    "comments": [{"author": "alice", "body": "Please prioritize this."}],
                },
                {
                    "id": 2,
                    "title": "Closed issue",
                    "body": "Ignore me.",
                    "state": "closed",
                },
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tracker = LocalFileTracker(path=issue_file, repo_root=tmp_path, dry_run=False)

    async def run_flow():
        issues = await tracker.list_open_issues()
        issue = await tracker.get_issue(1)
        comment = await tracker.post_comment(1, "RepoRepublic staged a maintainer note.")
        branch = await tracker.create_branch(
            issue_id=1,
            name="reporepublic/issue-1-fix-empty-input",
            workspace_path=workspace,
            commit_message="republic: address issue #1",
        )
        pr = await tracker.open_pr(
            issue_id=1,
            title="RepoRepublic: Fix empty input crash (#1)",
            body="Draft PR proposal staged locally.",
            head_branch=branch.payload["branch_name"],
            base_branch=branch.payload["base_branch"],
            draft=True,
        )
        labels = await tracker.set_issue_label(1, ["bug", "accepted"])
        return issues, issue, comment, branch, pr, labels

    issues, issue, comment, branch, pr, labels = asyncio.run(run_flow())

    assert [entry.id for entry in issues] == [1]
    assert issue.comments[0].author == "alice"
    assert comment.executed is True
    assert branch.executed is True
    assert pr.executed is True
    assert labels.executed is True

    sync_dir = tmp_path / ".ai-republic" / "sync" / "local-file" / "issue-1"
    assert sync_dir.exists()
    assert Path(comment.payload["stage_path"]).exists()
    assert Path(branch.payload["stage_path"]).exists()
    assert Path(pr.payload["stage_path"]).exists()
    assert Path(pr.payload["metadata_path"]).exists()
    assert Path(labels.payload["stage_path"]).exists()


def test_local_file_tracker_dry_run_blocks_sync_staging(tmp_path: Path) -> None:
    issue_file = tmp_path / "issues.json"
    issue_file.write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "number": 1,
                    "title": "Fix empty input crash",
                    "body": "Return an empty list.",
                }
            ]
        ),
        encoding="utf-8",
    )

    tracker = LocalFileTracker(path=issue_file, repo_root=tmp_path, dry_run=True)

    result = asyncio.run(tracker.post_comment(1, "dry-run"))

    assert result.executed is False
    assert "Dry-run" in result.reason
    assert not (tmp_path / ".ai-republic" / "sync").exists()


def test_build_tracker_supports_local_file_kind(demo_repo: Path) -> None:
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("kind: github", "kind: local_file")
        .replace("repo: demo/repo\n", "path: issues.json\n")
        .replace("mode: fixture\n", ""),
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    tracker = build_tracker(loaded, dry_run=True)

    assert isinstance(tracker, LocalFileTracker)


def test_local_markdown_tracker_reads_markdown_issue_directory_and_stages_sync_actions(tmp_path: Path) -> None:
    issue_dir = tmp_path / "issues"
    issue_dir.mkdir()
    (issue_dir / "001-fix-empty-input.md").write_text(
        "---\n"
        "id: 1\n"
        "title: Fix empty input crash\n"
        "labels:\n"
        "  - bug\n"
        "comments:\n"
        "  - author: alice\n"
        "    body: Please prioritize this.\n"
        "---\n\n"
        "Return an empty list.\n",
        encoding="utf-8",
    )
    (issue_dir / "002-closed-issue.md").write_text(
        "---\n"
        "id: 2\n"
        "title: Closed issue\n"
        "state: closed\n"
        "---\n\n"
        "Ignore me.\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tracker = LocalMarkdownTracker(path=issue_dir, repo_root=tmp_path, dry_run=False)

    async def run_flow():
        issues = await tracker.list_open_issues()
        issue = await tracker.get_issue(1)
        comment = await tracker.post_comment(1, "RepoRepublic staged a maintainer note.")
        branch = await tracker.create_branch(
            issue_id=1,
            name="reporepublic/issue-1-fix-empty-input",
            workspace_path=workspace,
            commit_message="republic: address issue #1",
        )
        pr = await tracker.open_pr(
            issue_id=1,
            title="RepoRepublic: Fix empty input crash (#1)",
            body="Draft PR proposal staged locally.",
            head_branch=branch.payload["branch_name"],
            base_branch=branch.payload["base_branch"],
            draft=True,
        )
        labels = await tracker.set_issue_label(1, ["bug", "accepted"])
        return issues, issue, comment, branch, pr, labels

    issues, issue, comment, branch, pr, labels = asyncio.run(run_flow())

    assert [entry.id for entry in issues] == [1]
    assert issue.comments[0].author == "alice"
    assert comment.executed is True
    assert branch.executed is True
    assert pr.executed is True
    assert labels.executed is True

    sync_dir = tmp_path / ".ai-republic" / "sync" / "local-markdown" / "issue-1"
    assert sync_dir.exists()

    comment_path = Path(comment.payload["stage_path"])
    assert comment_path.exists()
    assert "action: post_comment" in comment_path.read_text(encoding="utf-8")

    branch_path = Path(branch.payload["stage_path"])
    assert branch_path.exists()
    branch_payload = json.loads(branch_path.read_text(encoding="utf-8"))
    assert branch_payload["branch_name"] == "reporepublic/issue-1-fix-empty-input"
    assert branch_payload["action"] == "branch"

    pr_body_path = Path(pr.payload["stage_path"])
    pr_metadata_path = Path(pr.payload["metadata_path"])
    assert pr_body_path.exists()
    assert pr_metadata_path.exists()
    assert "Draft PR proposal staged locally." in pr_body_path.read_text(encoding="utf-8")
    pr_metadata = json.loads(pr_metadata_path.read_text(encoding="utf-8"))
    assert pr_metadata["draft"] is True
    assert pr.payload["url"] == str(pr_body_path)

    label_path = Path(labels.payload["stage_path"])
    assert label_path.exists()
    label_payload = json.loads(label_path.read_text(encoding="utf-8"))
    assert label_payload["labels"] == ["bug", "accepted"]


def test_local_markdown_tracker_dry_run_blocks_sync_staging(tmp_path: Path) -> None:
    issue_dir = tmp_path / "issues"
    issue_dir.mkdir()
    (issue_dir / "001-fix-empty-input.md").write_text(
        "# Fix empty input crash\n\nReturn an empty list.\n",
        encoding="utf-8",
    )

    tracker = LocalMarkdownTracker(path=issue_dir, repo_root=tmp_path, dry_run=True)

    result = asyncio.run(tracker.post_comment(1, "dry-run"))

    assert result.executed is False
    assert "Dry-run" in result.reason
    assert not (tmp_path / ".ai-republic" / "sync").exists()


def test_build_tracker_supports_local_markdown_kind(demo_repo: Path) -> None:
    issue_dir = demo_repo / "issues"
    issue_dir.mkdir()
    (issue_dir / "001-demo.md").write_text("# Demo issue\n\nTrack from markdown.\n", encoding="utf-8")
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("kind: github", "kind: local_markdown")
        .replace("repo: demo/repo\n", "path: issues\n")
        .replace("mode: fixture\n", ""),
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    tracker = build_tracker(loaded, dry_run=True)

    assert isinstance(tracker, LocalMarkdownTracker)


def test_redact_remote_url_removes_embedded_credentials() -> None:
    assert (
        _redact_remote_url("https://x-access-token:secret@github.com/demo/repo.git")
        == "https://github.com/demo/repo.git"
    )
    assert _redact_remote_url("git@github.com:demo/repo.git") == "git@github.com:demo/repo.git"


class _SpyLogger:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages

    def warning(self, message: str, extra: dict | None = None) -> None:
        if extra:
            rendered = f"{message} {extra}"
        else:
            rendered = message
        self.messages.append(rendered)


@pytest.mark.skipif(
    os.getenv("GITHUB_E2E") != "1" and os.getenv("REPOREPUBLIC_GITHUB_E2E") != "1",
    reason="Set GITHUB_E2E=1 or REPOREPUBLIC_GITHUB_E2E=1 to run the live GitHub tracker test.",
)
def test_github_tracker_live_read_only() -> None:
    repo = os.getenv("REPOREPUBLIC_GITHUB_TEST_REPO") or os.getenv("GITHUB_TEST_REPO")
    token = os.getenv("GITHUB_TOKEN")
    issue_id_raw = os.getenv("REPOREPUBLIC_GITHUB_TEST_ISSUE") or os.getenv("GITHUB_TEST_ISSUE")

    if not token:
        pytest.skip("GITHUB_TOKEN is required for the live GitHub tracker test.")
    if not repo:
        pytest.skip(
            "Set REPOREPUBLIC_GITHUB_TEST_REPO (or GITHUB_TEST_REPO) to a readable repo slug."
        )

    issue_id = int(issue_id_raw) if issue_id_raw else None
    tracker = GitHubTracker(
        repo=repo,
        api_url="https://api.github.com",
        token_env="GITHUB_TOKEN",
        repo_root=Path.cwd(),
        mode=TrackerMode.REST,
        fixtures_path=None,
        allow_write_comments=False,
        allow_open_pr=False,
        dry_run=False,
    )

    async def run_flow():
        issues = await tracker.list_open_issues()
        target_issue_id = issue_id or (issues[0].id if issues else None)
        if target_issue_id is None:
            await tracker.aclose()
            return issues, None
        issue = await tracker.get_issue(target_issue_id)
        await tracker.aclose()
        return issues, issue

    issues, issue = asyncio.run(run_flow())
    if issue is None:
        pytest.skip(
            "No open issues were found. Set REPOREPUBLIC_GITHUB_TEST_ISSUE to pin a known issue."
        )

    assert isinstance(issues, list)
    assert issue.id > 0
    assert issue.title
    assert issue.fingerprint()
    assert issue.url is None or issue.url.startswith("https://")


def _load_live_github_test_context(
    *,
    repo_envs: tuple[str, ...],
    issue_envs: tuple[str, ...] = (),
    require_issue: bool = False,
) -> tuple[str, str, int | None]:
    token = os.getenv("GITHUB_TOKEN")
    repo = next((os.getenv(name) for name in repo_envs if os.getenv(name)), None)
    issue_raw = next((os.getenv(name) for name in issue_envs if os.getenv(name)), None)
    if not token:
        pytest.skip("GITHUB_TOKEN is required for the live GitHub publish test.")
    if not repo:
        pytest.skip(
            "Set one of "
            + ", ".join(repo_envs)
            + " to point at a writable sandbox repo slug."
        )
    issue_id = int(issue_raw) if issue_raw else None
    if require_issue and issue_id is None:
        pytest.skip("Set a live GitHub test issue id for the sandbox repo.")
    return repo, token, issue_id


async def _github_api_request(
    *,
    method: str,
    repo: str,
    token: str,
    path: str,
    json_payload: dict[str, object] | None = None,
    ok_statuses: tuple[int, ...] = (200, 201, 204),
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.request(
            method,
            f"https://api.github.com{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json=json_payload,
        )
    if response.status_code not in ok_statuses:
        raise AssertionError(
            f"GitHub cleanup request failed for {repo} {method} {path}: "
            f"{response.status_code} {response.text}"
        )
    return response


def _authenticated_https_remote(repo: str, token: str) -> str:
    return f"https://x-access-token:{quote(token, safe='')}@github.com/{repo}.git"


@pytest.mark.skipif(
    os.getenv("REPOREPUBLIC_GITHUB_WRITE_E2E") != "1",
    reason="Set REPOREPUBLIC_GITHUB_WRITE_E2E=1 to run the live GitHub comment write test.",
)
def test_github_tracker_live_comment_write() -> None:
    repo, token, issue_id = _load_live_github_test_context(
        repo_envs=("REPOREPUBLIC_GITHUB_WRITE_TEST_REPO", "REPOREPUBLIC_GITHUB_TEST_REPO"),
        issue_envs=("REPOREPUBLIC_GITHUB_WRITE_TEST_ISSUE", "REPOREPUBLIC_GITHUB_TEST_ISSUE"),
        require_issue=True,
    )
    assert issue_id is not None

    async def run_flow() -> tuple[object, int | None]:
        tracker = GitHubTracker(
            repo=repo,
            api_url="https://api.github.com",
            token_env="GITHUB_TOKEN",
            repo_root=Path.cwd(),
            mode=TrackerMode.REST,
            fixtures_path=None,
            allow_write_comments=True,
            allow_open_pr=False,
            dry_run=False,
        )
        comment_id: int | None = None
        try:
            marker = f"RepoRepublic live comment E2E {int(time.time())}"
            result = await tracker.post_comment(issue_id, marker)
            payload = result.payload if isinstance(result.payload, dict) else {}
            raw_comment_id = payload.get("comment_id")
            comment_id = raw_comment_id if isinstance(raw_comment_id, int) else None
            return result, comment_id
        finally:
            await tracker.aclose()

    result, comment_id = asyncio.run(run_flow())
    try:
        assert result.executed is True
        payload = result.payload if isinstance(result.payload, dict) else {}
        assert payload.get("url")
        assert isinstance(comment_id, int) and comment_id > 0
    finally:
        if isinstance(comment_id, int):
            asyncio.run(
                _github_api_request(
                    method="DELETE",
                    repo=repo,
                    token=token,
                    path=f"/repos/{repo}/issues/comments/{comment_id}",
                    ok_statuses=(204,),
                )
            )


@pytest.mark.skipif(
    os.getenv("REPOREPUBLIC_GITHUB_PR_E2E") != "1",
    reason="Set REPOREPUBLIC_GITHUB_PR_E2E=1 to run the live GitHub draft PR publish test.",
)
def test_github_tracker_live_draft_pr_publish(tmp_path: Path) -> None:
    repo, token, issue_id = _load_live_github_test_context(
        repo_envs=("REPOREPUBLIC_GITHUB_PR_TEST_REPO", "REPOREPUBLIC_GITHUB_WRITE_TEST_REPO", "REPOREPUBLIC_GITHUB_TEST_REPO"),
        issue_envs=("REPOREPUBLIC_GITHUB_PR_TEST_ISSUE", "REPOREPUBLIC_GITHUB_WRITE_TEST_ISSUE", "REPOREPUBLIC_GITHUB_TEST_ISSUE"),
        require_issue=True,
    )
    assert issue_id is not None

    source_repo = tmp_path / "source"
    workspace = tmp_path / "workspace"
    subprocess.run(
        ["git", "clone", "--depth", "1", f"https://github.com/{repo}.git", str(source_repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "remote", "set-url", "origin", _authenticated_https_remote(repo, token)],
        check=True,
        capture_output=True,
        text=True,
    )
    shutil.copytree(source_repo, workspace, ignore=shutil.ignore_patterns(".git"))
    marker = f"reporepublic-pr-e2e-{int(time.time())}"
    target_file = workspace / "README.md"
    if target_file.exists():
        target_file.write_text(
            target_file.read_text(encoding="utf-8")
            + f"\n<!-- {marker} -->\n",
            encoding="utf-8",
        )
    else:
        (workspace / "REPOREPUBLIC_E2E.md").write_text(f"# {marker}\n", encoding="utf-8")

    async def run_flow() -> tuple[object, object, str | None, int | None]:
        tracker = GitHubTracker(
            repo=repo,
            api_url="https://api.github.com",
            token_env="GITHUB_TOKEN",
            repo_root=source_repo,
            mode=TrackerMode.REST,
            fixtures_path=None,
            allow_write_comments=False,
            allow_open_pr=True,
            dry_run=False,
        )
        branch_name: str | None = None
        pr_number: int | None = None
        try:
            repo_info = await tracker.get_repo_info()
            branch_result = await tracker.create_branch(
                issue_id=issue_id,
                name=f"codex/live-pr-e2e-{issue_id}-{marker}",
                workspace_path=workspace,
                commit_message=f"republic: live pr e2e {marker}",
            )
            branch_payload = branch_result.payload if isinstance(branch_result.payload, dict) else {}
            branch_name = branch_payload.get("branch_name") if isinstance(branch_payload.get("branch_name"), str) else None
            if branch_result.executed is not True or not branch_name:
                raise AssertionError(branch_result.reason)
            pr_result = await tracker.open_pr(
                issue_id=issue_id,
                title=f"RepoRepublic: live publish E2E ({marker})",
                body=f"RepoRepublic live draft PR smoke for issue #{issue_id}.\n\nMarker: {marker}",
                head_branch=branch_name,
                base_branch=str(repo_info.get("default_branch") or branch_payload.get("base_branch") or "main"),
                draft=True,
            )
            pr_payload = pr_result.payload if isinstance(pr_result.payload, dict) else {}
            raw_pr_number = pr_payload.get("number")
            pr_number = raw_pr_number if isinstance(raw_pr_number, int) else None
            return branch_result, pr_result, branch_name, pr_number
        finally:
            await tracker.aclose()

    branch_result, pr_result, branch_name, pr_number = asyncio.run(run_flow())
    cleanup_errors: list[str] = []
    try:
        assert branch_result.executed is True
        assert pr_result.executed is True
        pr_payload = pr_result.payload if isinstance(pr_result.payload, dict) else {}
        assert isinstance(pr_number, int) and pr_number > 0
        assert pr_payload.get("url")
        assert pr_payload.get("draft") is True
    finally:
        if isinstance(pr_number, int):
            try:
                asyncio.run(
                    _github_api_request(
                        method="PATCH",
                        repo=repo,
                        token=token,
                        path=f"/repos/{repo}/pulls/{pr_number}",
                        json_payload={"state": "closed"},
                        ok_statuses=(200,),
                    )
                )
            except AssertionError as exc:
                cleanup_errors.append(str(exc))
        if isinstance(branch_name, str) and branch_name:
            try:
                asyncio.run(
                    _github_api_request(
                        method="DELETE",
                        repo=repo,
                        token=token,
                        path=f"/repos/{repo}/git/refs/heads/{quote(branch_name, safe='')}",
                        ok_statuses=(204, 422, 404),
                    )
                )
            except AssertionError as exc:
                cleanup_errors.append(str(exc))
        if cleanup_errors:
            raise AssertionError("; ".join(cleanup_errors))
