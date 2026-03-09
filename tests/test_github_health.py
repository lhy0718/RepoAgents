from __future__ import annotations

from pathlib import Path

from reporepublic.config import load_config
from reporepublic.github_health import (
    build_github_smoke_snapshot,
    collect_github_auth_snapshot,
    collect_github_origin_snapshot,
    collect_github_publish_readiness,
    extract_git_remote_repo_slug,
    render_github_smoke_markdown,
)
from reporepublic.models import IssueComment, IssueRef


def test_collect_github_auth_snapshot_requires_token_for_rest_even_with_gh_auth(
    demo_repo: Path,
    monkeypatch,
) -> None:
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("mode: fixture", "mode: rest"),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("reporepublic.github_health.shutil.which", lambda command: "/opt/test/gh")

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr("reporepublic.github_health.subprocess.run", lambda *args, **kwargs: Completed())

    snapshot = collect_github_auth_snapshot(loaded)

    assert snapshot["status"] == "warn"
    assert "still requires GITHUB_TOKEN" in snapshot["message"]
    assert snapshot["gh_authenticated"] is True


def test_collect_github_origin_snapshot_detects_mismatched_origin(
    demo_repo: Path,
    monkeypatch,
) -> None:
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("mode: fixture", "mode: rest"),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)

    monkeypatch.setattr("reporepublic.github_health.is_git_repository", lambda path: True)
    monkeypatch.setattr(
        "reporepublic.github_health.run_git",
        lambda args, cwd: "git@github.com:demo/other-repo.git",
    )

    snapshot = collect_github_origin_snapshot(loaded)

    assert snapshot["status"] == "issues"
    assert snapshot["repo_slug"] == "demo/other-repo"
    assert snapshot["matches_tracker_repo"] is False


def test_collect_github_publish_readiness_warns_when_pr_publish_is_not_ready(
    demo_repo: Path,
) -> None:
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
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


def test_build_github_smoke_snapshot_collects_repo_and_issue_details(
    demo_repo: Path,
) -> None:
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
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


def test_extract_git_remote_repo_slug_handles_https_and_ssh() -> None:
    assert extract_git_remote_repo_slug("git@github.com:demo/repo.git") == "demo/repo"
    assert extract_git_remote_repo_slug("https://github.com/demo/repo.git") == "demo/repo"
