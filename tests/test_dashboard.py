from __future__ import annotations

from pathlib import Path
import json

from reporepublic.config import load_config
from reporepublic.dashboard import build_dashboard
from reporepublic.models import ExternalActionResult, RunLifecycle, RunRecord
from reporepublic.orchestrator import RunStateStore


def test_build_dashboard_renders_recent_runs_and_links(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    store = RunStateStore(loaded.state_dir / "runs.json")
    artifact_dir = loaded.artifacts_dir / "issue-1" / "run-1"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    reviewer_md = artifact_dir / "reviewer.md"
    reviewer_md.write_text("# Review\n", encoding="utf-8")
    workspace_dir = loaded.workspace_root / "issue-1" / "run-1" / "repo"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    sync_applied_dir = loaded.sync_applied_dir / "local-markdown" / "issue-1"
    sync_applied_dir.mkdir(parents=True, exist_ok=True)
    archived_pr = sync_applied_dir / "20260308T010202000001Z-pr.json"
    archived_pr.write_text(
        json.dumps(
            {
                "action": "pr",
                "issue_id": 1,
                "title": "RepoRepublic: Fix empty input crash (#1)",
                "head_branch": "reporepublic/issue-1-fix-empty-input",
                "base_branch": "main",
                "staged_at": "20260308T010202000001Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    archived_pr_body = sync_applied_dir / "20260308T010203000001Z-pr-body.md"
    archived_pr_body.write_text(
        "---\n"
        "issue_id: 1\n"
        "head_branch: reporepublic/issue-1-fix-empty-input\n"
        "base_branch: main\n"
        "staged_at: 20260308T010203000001Z\n"
        "---\n\n"
        "Draft PR proposal staged locally.\n",
        encoding="utf-8",
    )
    manifest_path = sync_applied_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "entry_key": "local-markdown:local-markdown/issue-1/20260308T010202000001Z-pr.json",
                    "tracker": "local-markdown",
                    "issue_id": 1,
                    "action": "pr",
                    "format": "json",
                    "applied_at": "2026-03-08T01:02:02+00:00",
                    "staged_at": "20260308T010202000001Z",
                    "summary": "Draft PR metadata archived for handoff.",
                    "normalized": {
                        "artifact_role": "pr-proposal",
                        "issue_key": "issue:1",
                        "bundle_key": "issue:1|head:reporepublic/issue-1-fix-empty-input",
                        "refs": {
                            "head": "reporepublic/issue-1-fix-empty-input",
                            "base": "main",
                        },
                        "links": {
                            "self": "local-markdown/issue-1/20260308T010202000001Z-pr.json",
                        },
                    },
                    "source_relative_path": "local-markdown/issue-1/20260308T010202000001Z-pr.json",
                    "archived_relative_path": "local-markdown/issue-1/20260308T010202000001Z-pr.json",
                    "archived_path": str(archived_pr),
                    "effect": "Archived PR metadata handoff.",
                    "handoff": {
                        "group_key": "issue:1|head:reporepublic/issue-1-fix-empty-input",
                        "group_size": 2,
                        "group_index": 0,
                        "group_actions": ["pr", "pr-body"],
                        "related_entry_keys": [
                            "local-markdown:local-markdown/issue-1/20260308T010202000001Z-pr.json",
                            "local-markdown:local-markdown/issue-1/20260308T010203000001Z-pr-body.md",
                        ],
                        "related_source_paths": [
                            "local-markdown/issue-1/20260308T010202000001Z-pr.json",
                            "local-markdown/issue-1/20260308T010203000001Z-pr-body.md",
                        ],
                    },
                },
                {
                    "entry_key": "local-markdown:local-markdown/issue-1/20260308T010203000001Z-pr-body.md",
                    "tracker": "local-markdown",
                    "issue_id": 1,
                    "action": "pr-body",
                    "format": "markdown",
                    "applied_at": "2026-03-08T01:02:03+00:00",
                    "staged_at": "20260308T010203000001Z",
                    "summary": "Draft PR body archived for handoff.",
                    "normalized": {
                        "artifact_role": "pr-body-proposal",
                        "issue_key": "issue:1",
                        "bundle_key": "issue:1|head:reporepublic/issue-1-fix-empty-input",
                        "refs": {
                            "head": "reporepublic/issue-1-fix-empty-input",
                            "base": "main",
                        },
                        "links": {
                            "metadata_artifact": "local-markdown/issue-1/20260308T010202000001Z-pr.json",
                            "self": "local-markdown/issue-1/20260308T010203000001Z-pr-body.md",
                        },
                    },
                    "source_relative_path": "local-markdown/issue-1/20260308T010203000001Z-pr-body.md",
                    "archived_relative_path": "local-markdown/issue-1/20260308T010203000001Z-pr-body.md",
                    "archived_path": str(archived_pr_body),
                    "effect": "Archived PR body handoff.",
                    "handoff": {
                        "group_key": "issue:1|head:reporepublic/issue-1-fix-empty-input",
                        "group_size": 2,
                        "group_index": 1,
                        "group_actions": ["pr", "pr-body"],
                        "related_entry_keys": [
                            "local-markdown:local-markdown/issue-1/20260308T010202000001Z-pr.json",
                            "local-markdown:local-markdown/issue-1/20260308T010203000001Z-pr-body.md",
                        ],
                        "related_source_paths": [
                            "local-markdown/issue-1/20260308T010202000001Z-pr.json",
                            "local-markdown/issue-1/20260308T010203000001Z-pr-body.md",
                        ],
                    },
                },
            ],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    store.upsert(
        RunRecord(
            run_id="run-1",
            issue_id=1,
            issue_title="Fix empty input crash",
            fingerprint="fp-1",
            status=RunLifecycle.FAILED,
            backend_mode="mock",
            workspace_path=str(workspace_dir),
            summary="Reviewer requested follow-up before publish.",
            last_error="Tests did not cover the empty-string branch.",
            role_artifacts={"reviewer": str(reviewer_md)},
            external_actions=[
                ExternalActionResult(
                    action="post_comment",
                    executed=False,
                    reason="Dry-run mode blocks external writes.",
                    payload={"url": "https://github.example/demo/repo/issues/1#issuecomment-1"},
                )
            ],
        )
    )

    result = build_dashboard(
        loaded,
        limit=10,
        refresh_seconds=30,
        formats=("html", "json", "markdown"),
    )
    html = result.output_path.read_text(encoding="utf-8")
    dashboard_json = result.exported_paths["json"].read_text(encoding="utf-8")
    dashboard_markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")
    payload = json.loads(dashboard_json)

    assert result.total_runs == 1
    assert result.visible_runs == 1
    assert set(result.exported_paths) == {"html", "json", "markdown"}
    assert "RepoRepublic Operations Dashboard" in html
    assert "Fix empty input crash" in html
    assert "Tests did not cover the empty-string branch." in html
    assert "reviewer" in html
    assert "https://github.example/demo/repo/issues/1#issuecomment-1" in html
    assert "Sync handoffs" in html
    assert "pr-body-proposal" in html
    assert "metadata_artifact" in html
    assert "manifest.json" in html
    assert 'id="run-search"' in html
    assert 'id="status-filter"' in html
    assert 'id="refresh-interval"' in html
    assert 'data-status="failed"' in html
    assert 'data-default-refresh-seconds="30"' in html
    assert "window.location.reload()" in html
    assert payload["counts"]["total_runs"] == 1
    assert payload["counts"]["total_sync_handoffs"] == 2
    assert payload["runs"][0]["run_id"] == "run-1"
    assert payload["runs"][0]["external_actions"][0]["action"] == "post_comment"
    assert payload["sync_handoffs"][0]["artifact_role"] == "pr-body-proposal"
    assert payload["sync_handoffs"][0]["normalized_links"][0]["label"] == "metadata_artifact"
    assert payload["sync_handoffs"][0]["manifest_path"] == str(manifest_path)
    assert "# RepoRepublic Dashboard Snapshot" in dashboard_markdown
    assert "### Issue #1: Fix empty input crash" in dashboard_markdown
    assert "- status: failed" in dashboard_markdown
    assert "## Sync handoffs" in dashboard_markdown
    assert "- bundle_key: issue:1|head:reporepublic/issue-1-fix-empty-input" in dashboard_markdown
