from __future__ import annotations

from pathlib import Path

from repoagents.config import load_config
from repoagents.github_health import (
    build_github_smoke_snapshot,
    collect_github_branch_policy_snapshot,
    collect_github_auth_snapshot,
    collect_github_live_repo_snapshots,
    collect_github_origin_snapshot,
    collect_github_publish_readiness,
    extract_git_remote_repo_slug,
    render_github_smoke_markdown,
)
from repoagents.models import IssueComment, IssueRef


def test_collect_github_auth_snapshot_requires_token_for_rest_even_with_gh_auth(
    demo_repo: Path,
    monkeypatch,
) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("mode: fixture", "mode: rest"),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("repoagents.github_health.shutil.which", lambda command: "/opt/test/gh")

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr("repoagents.github_health.subprocess.run", lambda *args, **kwargs: Completed())

    snapshot = collect_github_auth_snapshot(loaded)

    assert snapshot["status"] == "warn"
    assert "still requires GITHUB_TOKEN" in snapshot["message"]
    assert snapshot["gh_authenticated"] is True


def test_collect_github_origin_snapshot_detects_mismatched_origin(
    demo_repo: Path,
    monkeypatch,
) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("mode: fixture", "mode: rest"),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)

    monkeypatch.setattr("repoagents.github_health.is_git_repository", lambda path: True)
    monkeypatch.setattr(
        "repoagents.github_health.run_git",
        lambda args, cwd: "git@github.com:demo/other-repo.git",
    )

    snapshot = collect_github_origin_snapshot(loaded)

    assert snapshot["status"] == "issues"
    assert snapshot["repo_slug"] == "demo/other-repo"
    assert snapshot["matches_tracker_repo"] is False


def test_collect_github_publish_readiness_warns_when_pr_publish_is_not_ready(
    demo_repo: Path,
) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("mode: fixture", "mode: rest")
        .replace("allow_open_pr: false", "allow_open_pr: true"),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)

    readiness = collect_github_publish_readiness(
        loaded,
        auth_snapshot={"token_present": True},
        origin_snapshot={"status": "issues", "message": "git remote origin is not configured"},
    )

    assert readiness["status"] == "warn"
    assert readiness["pr_writes_ready"] is False
    assert "git remote origin is not configured" in readiness["message"]


def test_collect_github_publish_readiness_warns_when_repo_permissions_lack_push(
    demo_repo: Path,
) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("mode: fixture", "mode: rest")
        .replace("allow_open_pr: false", "allow_open_pr: true"),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)

    readiness = collect_github_publish_readiness(
        loaded,
        auth_snapshot={"token_present": True},
        origin_snapshot={"status": "ok", "message": "origin matches"},
        repo_access_snapshot={
            "status": "ok",
            "permissions": {"pull": True, "push": False},
        },
    )

    assert readiness["status"] == "warn"
    assert readiness["pr_writes_ready"] is False
    assert "push permission=false" in readiness["message"]


def test_collect_github_branch_policy_snapshot_warns_when_default_branch_is_unprotected(
    demo_repo: Path,
) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("mode: fixture", "mode: rest"),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)

    class FakeTracker:
        async def get_repo_info(self) -> dict[str, object]:
            return {
                "full_name": "demo/repo",
                "default_branch": "main",
                "private": False,
                "permissions": {"pull": True, "push": True},
            }

        async def get_branch_info(self, branch: str) -> dict[str, object]:
            assert branch == "main"
            return {
                "name": branch,
                "protected": False,
            }

        async def get_branch_protection(self, branch: str) -> dict[str, object]:
            raise AssertionError("unprotected branches should not fetch detailed protection")

    snapshot = __import__("asyncio").run(
        collect_github_branch_policy_snapshot(
            loaded,
            tracker=FakeTracker(),  # type: ignore[arg-type]
        )
    )

    assert snapshot["status"] == "warn"
    assert snapshot["protected"] is False
    assert "not protected" in snapshot["message"]


def test_collect_github_live_repo_snapshots_reads_branch_policy_details(
    demo_repo: Path,
) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("mode: fixture", "mode: rest")
        .replace("allow_open_pr: false", "allow_open_pr: true"),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)

    class FakeTracker:
        async def get_repo_info(self) -> dict[str, object]:
            return {
                "full_name": "demo/repo",
                "default_branch": "main",
                "private": False,
                "permissions": {"pull": True, "push": True},
            }

        async def get_branch_info(self, branch: str) -> dict[str, object]:
            return {
                "name": branch,
                "protected": True,
                "protection_url": "https://api.github.com/repos/demo/repo/branches/main/protection",
            }

        async def get_branch_protection(self, branch: str) -> dict[str, object]:
            return {
                "required_pull_request_reviews": {"required_approving_review_count": 1},
                "required_status_checks": {"strict": True, "contexts": ["pytest"]},
                "enforce_admins": {"enabled": True},
            }

        async def aclose(self) -> None:
            return None

    repo_access, branch_policy = __import__("asyncio").run(
        collect_github_live_repo_snapshots(
            loaded,
            tracker=FakeTracker(),  # type: ignore[arg-type]
        )
    )

    readiness = collect_github_publish_readiness(
        loaded,
        auth_snapshot={"token_present": True},
        origin_snapshot={"status": "ok", "message": "origin matches"},
        repo_access_snapshot=repo_access,
        branch_policy_snapshot=branch_policy,
    )

    assert repo_access["status"] == "ok"
    assert branch_policy["status"] == "ok"
    assert branch_policy["required_pull_request_reviews"] is True
    assert branch_policy["required_status_checks"] is True
    assert readiness["status"] == "ok"


def test_build_github_smoke_snapshot_collects_repo_and_issue_details(
    demo_repo: Path,
) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("mode: fixture", "mode: rest"),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)

    class FakeTracker:
        async def get_repo_info(self) -> dict[str, object]:
            return {
                "full_name": "demo/repo",
                "default_branch": "main",
                "private": False,
                "permissions": {"pull": True, "push": False},
            }

        async def get_branch_info(self, branch: str) -> dict[str, object]:
            return {
                "name": branch,
                "protected": True,
                "protection_url": "https://api.github.com/repos/demo/repo/branches/main/protection",
            }

        async def get_branch_protection(self, branch: str) -> dict[str, object]:
            return {
                "required_pull_request_reviews": {"required_approving_review_count": 1},
                "required_status_checks": {"strict": True, "contexts": ["pytest"]},
                "enforce_admins": {"enabled": True},
            }

        async def list_open_issues(self) -> list[IssueRef]:
            return [
                IssueRef.model_validate(
                    {
                        "id": 1,
                        "number": 1,
                        "title": "Fix empty input crash",
                        "labels": ["bug"],
                    }
                )
            ]

        async def get_issue(self, issue_id: int) -> IssueRef:
            return IssueRef.model_validate(
                {
                    "id": issue_id,
                    "number": issue_id,
                    "title": "Fix empty input crash",
                    "labels": ["bug"],
                    "comments": [
                        IssueComment.model_validate(
                            {
                                "author": "demo",
                                "body": "please fix",
                            }
                        )
                    ],
                }
            )

    snapshot = __import__("asyncio").run(
        build_github_smoke_snapshot(
            loaded=loaded,
            tracker=FakeTracker(),  # type: ignore[arg-type]
            issue_id=1,
            issue_limit=3,
        )
    )

    assert snapshot["summary"]["status"] in {"clean", "attention"}
    assert snapshot["repo_access"]["full_name"] == "demo/repo"
    assert snapshot["issues"]["count"] == 1
    assert snapshot["sampled_issue"]["issue_id"] == 1
    markdown = render_github_smoke_markdown(snapshot)
    assert "# GitHub smoke report" in markdown
    assert "## Publish readiness" in markdown


def test_build_github_smoke_snapshot_uses_configured_fixture_snapshot(
    demo_git_repo: Path,
) -> None:
    fixture_path = demo_git_repo / "github-smoke.fixture.json"
    fixture_path.write_text(
        """
{
  "summary": {
    "status": "attention",
    "message": "fixture smoke captured publish warnings",
    "open_issue_count": 2,
    "sampled_issue_id": 7,
    "auth_status": "ok",
    "repo_access_status": "ok",
    "branch_policy_status": "warn",
    "publish_status": "warn"
  },
  "repo_access": {
    "status": "ok",
    "message": "loaded repo metadata for demo/repo",
    "full_name": "demo/repo",
    "default_branch": "main",
    "permissions": {
      "pull": true,
      "push": true
    }
  },
  "branch_policy": {
    "status": "warn",
    "message": "default branch main is protected but missing one required status check context",
    "default_branch": "main",
    "warnings": [
      "default branch main is missing required status check context ci/smoke"
    ]
  },
  "publish": {
    "status": "warn",
    "message": "publish warnings captured in fixture"
  },
  "issues": {
    "status": "ok",
    "message": "loaded 2 open issue(s)",
    "count": 2
  },
  "sampled_issue": {
    "status": "ok",
    "message": "loaded issue #7",
    "issue_id": 7,
    "title": "Fixture issue"
  }
}
""".strip(),
        encoding="utf-8",
    )
    config_path = demo_git_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("mode: fixture", "mode: rest")
        .replace(
            "poll_interval_seconds: 60",
            "poll_interval_seconds: 60\n  smoke_fixture_path: github-smoke.fixture.json",
        ),
        encoding="utf-8",
    )
    loaded = load_config(demo_git_repo)

    class UnexpectedTracker:
        async def aclose(self) -> None:
            return None

    snapshot = __import__("asyncio").run(
        build_github_smoke_snapshot(
            loaded=loaded,
            tracker=UnexpectedTracker(),  # type: ignore[arg-type]
            issue_id=7,
            issue_limit=4,
        )
    )

    assert snapshot["summary"]["status"] == "attention"
    assert snapshot["summary"]["sampled_issue_id"] == 7
    assert snapshot["meta"]["tracker_repo"] == "demo/repo"
    assert snapshot["meta"]["fixture_path"] == str(fixture_path.resolve())
    assert snapshot["branch_policy"]["status"] == "warn"
    assert snapshot["publish"]["status"] == "warn"


def test_extract_git_remote_repo_slug_handles_https_and_ssh() -> None:
    assert extract_git_remote_repo_slug("git@github.com:demo/repo.git") == "demo/repo"
    assert extract_git_remote_repo_slug("https://github.com/demo/repo.git") == "demo/repo"
