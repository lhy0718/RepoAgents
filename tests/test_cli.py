from __future__ import annotations

import importlib
import json
from datetime import timedelta
from pathlib import Path

from typer.testing import CliRunner
import yaml

from reporepublic.cli.app import app
from reporepublic.config import load_config
from reporepublic.models import ExternalActionResult, RunLifecycle, RunRecord
from reporepublic.models.domain import utc_now
from reporepublic.orchestrator import RunStateStore


runner = CliRunner()
app_module = importlib.import_module("reporepublic.cli.app")


def test_cli_init_creates_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "issues.json").write_text("[]", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "init",
            "--preset",
            "python-library",
            "--fixture-issues",
            "issues.json",
            "--tracker-repo",
            "demo/repo",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert (tmp_path / ".ai-republic" / "reporepublic.yaml").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "WORKFLOW.md").exists()
    assert (tmp_path / ".github" / "workflows" / "republic-check.yml").exists()
    assert (tmp_path / ".ai-republic" / "roles" / "qa.md").exists()
    assert (tmp_path / ".ai-republic" / "prompts" / "qa.txt.j2").exists()


def test_cli_init_interactive_prompts_for_missing_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "issues.json").write_text("[]", encoding="utf-8")

    result = runner.invoke(
        app,
        ["init"],
        input="python-library\ngithub\ndemo/repo\nmock\ny\nissues.json\n",
        catch_exceptions=False,
    )

    loaded = load_config(tmp_path)
    assert result.exit_code == 0
    assert "Interactive RepoRepublic initialization" in result.stdout
    assert "Preset [docs-only/python-library/research-project/web-app]" in result.stdout
    assert "Tracker kind [github/local_file/local_markdown]" in result.stdout
    assert "Tracker repo" in result.stdout
    assert "Backend mode [codex/mock]" in result.stdout
    assert loaded.data.tracker.repo == "demo/repo"
    assert loaded.data.tracker.mode.value == "fixture"
    assert loaded.data.tracker.fixtures_path == "issues.json"
    assert loaded.data.llm.mode.value == "mock"


def test_cli_init_local_file_tracker_writes_local_tracker_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "issues.json").write_text("[]", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "init",
            "--tracker-kind",
            "local_file",
            "--tracker-path",
            "issues.json",
        ],
        catch_exceptions=False,
    )

    loaded = load_config(tmp_path)
    assert result.exit_code == 0
    assert loaded.data.tracker.kind.value == "local_file"
    assert loaded.data.tracker.path == "issues.json"
    assert loaded.data.tracker.repo is None


def test_cli_init_local_markdown_tracker_writes_local_tracker_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "issues").mkdir()

    result = runner.invoke(
        app,
        [
            "init",
            "--tracker-kind",
            "local_markdown",
            "--tracker-path",
            "issues",
        ],
        catch_exceptions=False,
    )

    loaded = load_config(tmp_path)
    assert result.exit_code == 0
    assert loaded.data.tracker.kind.value == "local_markdown"
    assert loaded.data.tracker.path == "issues"
    assert loaded.data.tracker.repo is None


def test_cli_init_backend_flag_updates_config_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["init", "--backend", "mock"],
        catch_exceptions=False,
    )

    loaded = load_config(tmp_path)
    assert result.exit_code == 0
    assert loaded.data.llm.mode.value == "mock"


def test_cli_init_upgrade_preserves_local_drift_and_restores_missing_files(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    drifted = demo_repo / ".ai-republic" / "roles" / "triage.md"
    drifted.write_text("custom local triage guidance\n", encoding="utf-8")
    missing = demo_repo / ".ai-republic" / "prompts" / "reviewer.txt.j2"
    missing.unlink()

    result = runner.invoke(app, ["init", "--upgrade"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "preserve: .ai-republic/roles/triage.md" in result.stdout
    assert "create: .ai-republic/prompts/reviewer.txt.j2" in result.stdout
    assert "Local modifications were preserved." in result.stdout
    assert drifted.read_text(encoding="utf-8") == "custom local triage guidance\n"
    assert missing.exists()


def test_cli_init_upgrade_force_refreshes_drifted_managed_files(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    drifted = demo_repo / ".ai-republic" / "roles" / "triage.md"
    drifted.write_text("custom local triage guidance\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--upgrade", "--force"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "refresh: .ai-republic/roles/triage.md" in result.stdout
    assert "Applied upgrades:" in result.stdout
    assert "custom local triage guidance" not in drifted.read_text(encoding="utf-8")


def test_cli_dry_run_outputs_preview(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    result = runner.invoke(app, ["run", "--dry-run"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Issue #1: Fix empty input crash" in result.stdout
    assert "roles: triage, planner, engineer, reviewer" in result.stdout
    assert "blocked_side_effects" in result.stdout
    assert "comment_preview:" in result.stdout
    assert "pr_title_preview:" in result.stdout
    assert "pr_body_preview:" in result.stdout


def test_cli_trigger_runs_single_issue(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)

    result = runner.invoke(app, ["trigger", "1"], catch_exceptions=False)

    store = RunStateStore(demo_repo / ".ai-republic" / "state" / "runs.json")
    assert result.exit_code == 0
    assert "Triggered issue #1." in result.stdout
    assert "issue=1" in result.stdout
    assert "issue=2" not in result.stdout
    assert store.get(1) is not None
    assert store.get(2) is None


def test_cli_webhook_dry_run_triggers_single_issue(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    payload_path = demo_repo / "webhook.json"
    payload_path.write_text(
        json.dumps(
            {
                "action": "opened",
                "issue": {"number": 1, "state": "open"},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["webhook", "--event", "issues", "--payload", str(payload_path), "--dry-run"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Webhook decision: provider=github event=issues action=opened issue=1 should_run=True" in result.stdout
    assert "Issue #1: Fix empty input crash" in result.stdout
    assert "Issue #2" not in result.stdout


def test_cli_webhook_ignores_unsupported_payload(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    payload_path = demo_repo / "ignored-webhook.json"
    payload_path.write_text(
        json.dumps(
            {
                "action": "edited",
                "issue": {"number": 2, "state": "closed"},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["webhook", "--event", "issues", "--payload", str(payload_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "should_run=False" in result.stdout
    assert "issue is closed" in result.stdout


def test_cli_run_warns_on_dirty_working_tree(demo_git_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_git_repo)
    (demo_git_repo / "parser.py").write_text(
        "def parse_items(raw: str) -> list[str]:\n    return []\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["run", "--dry-run"], catch_exceptions=False)
    combined = result.stdout + result.stderr

    assert result.exit_code == 0
    assert "Workspace policy warning: dirty working tree detected" in combined
    assert "Issue #1: Fix empty input crash" in result.stdout


def test_cli_run_blocks_on_dirty_working_tree_when_configured(
    demo_git_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_git_repo)
    config_path = demo_git_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("dirty_policy: warn", "dirty_policy: block"),
        encoding="utf-8",
    )
    (demo_git_repo / "parser.py").write_text(
        "def parse_items(raw: str) -> list[str]:\n    return []\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["run", "--dry-run"], catch_exceptions=False)
    combined = result.stdout + result.stderr

    assert result.exit_code == 1
    assert "Workspace policy blocked run: dirty working tree detected" in combined


def test_cli_status_filters_single_issue(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    store = RunStateStore(demo_repo / ".ai-republic" / "state" / "runs.json")
    store.upsert(
        RunRecord(
            run_id="run-1",
            issue_id=1,
            issue_title="Fix empty input crash",
            fingerprint="fp-1",
            status=RunLifecycle.COMPLETED,
            backend_mode="mock",
            summary="Completed run.",
        )
    )
    store.upsert(
        RunRecord(
            run_id="run-2",
            issue_id=2,
            issue_title="Improve README quickstart",
            fingerprint="fp-2",
            status=RunLifecycle.RETRY_PENDING,
            backend_mode="codex",
            next_retry_at=utc_now(),
            workspace_path="/tmp/republic/workspace",
            last_error="temporary failure",
            external_actions=[
                ExternalActionResult(
                    action="post_comment",
                    executed=False,
                    reason="Dry-run mode blocks external writes.",
                )
            ],
        )
    )

    result = runner.invoke(app, ["status", "--issue", "2"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "issue=2 run_id=run-2" in result.stdout
    assert "issue=1 run_id=run-1" not in result.stdout
    assert "next_retry_at:" in result.stdout
    assert "workspace: /tmp/republic/workspace" in result.stdout
    assert "external_actions:" in result.stdout


def test_cli_clean_sync_applied_dry_run_previews_manifest_aware_retention(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    _configure_sync_retention(demo_repo, keep_groups=1)
    sync_issue_root = demo_repo / ".ai-republic" / "sync-applied" / "local-markdown" / "issue-1"
    sync_issue_root.mkdir(parents=True, exist_ok=True)
    new_comment = sync_issue_root / "20260308T010101000001Z-comment.md"
    old_branch = sync_issue_root / "20260308T010001000001Z-branch.json"
    old_pr = sync_issue_root / "20260308T010002000001Z-pr.json"
    orphan = sync_issue_root / "20260308T005959000001Z-orphan.md"
    new_comment.write_text("---\nissue_id: 1\n---\n\nRecent comment handoff.\n", encoding="utf-8")
    old_branch.write_text('{"action":"branch","issue_id":1}\n', encoding="utf-8")
    old_pr.write_text('{"action":"pr","issue_id":1}\n', encoding="utf-8")
    orphan.write_text("orphan\n", encoding="utf-8")
    (sync_issue_root / "manifest.json").write_text(
        json.dumps(
            [
                _manifest_entry(
                    tracker="local-markdown",
                    issue_id=1,
                    action="branch",
                    applied_at="2026-03-08T01:00:01+00:00",
                    staged_at="20260308T010001000001Z",
                    archived_path=old_branch,
                    group_key="issue:1|head:reporepublic/old-branch",
                    artifact_role="branch-proposal",
                ),
                _manifest_entry(
                    tracker="local-markdown",
                    issue_id=1,
                    action="pr",
                    applied_at="2026-03-08T01:00:02+00:00",
                    staged_at="20260308T010002000001Z",
                    archived_path=old_pr,
                    group_key="issue:1|head:reporepublic/old-branch",
                    artifact_role="pr-proposal",
                ),
                _manifest_entry(
                    tracker="local-markdown",
                    issue_id=1,
                    action="comment",
                    applied_at="2026-03-08T01:01:01+00:00",
                    staged_at="20260308T010101000001Z",
                    archived_path=new_comment,
                    group_key="issue:1|comment",
                    artifact_role="comment-proposal",
                ),
            ],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["clean", "--sync-applied", "--dry-run"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Clean preview:" in result.stdout
    assert "sync-applied-manifest:" in result.stdout
    assert "keep_groups=1/2" in result.stdout
    assert "sync-applied-archive:" in result.stdout
    assert "20260308T010001000001Z-branch.json" in result.stdout
    assert "20260308T010002000001Z-pr.json" in result.stdout
    assert "20260308T005959000001Z-orphan.md" in result.stdout


def test_cli_clean_sync_applied_prunes_old_groups_and_repairs_manifest(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    _configure_sync_retention(demo_repo, keep_groups=1)
    sync_issue_root = demo_repo / ".ai-republic" / "sync-applied" / "local-file" / "issue-1"
    sync_issue_root.mkdir(parents=True, exist_ok=True)
    recent_comment = sync_issue_root / "20260308T010101000001Z-comment.md"
    stale_branch = sync_issue_root / "20260308T010001000001Z-branch.json"
    dangling_pr_body = sync_issue_root / "20260308T010003000001Z-pr-body.md"
    orphan = sync_issue_root / "20260308T005959000001Z-orphan.md"
    recent_comment.write_text("---\nissue_id: 1\n---\n\nRecent comment handoff.\n", encoding="utf-8")
    stale_branch.write_text('{"action":"branch","issue_id":1}\n', encoding="utf-8")
    orphan.write_text("orphan\n", encoding="utf-8")
    manifest_path = sync_issue_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                _manifest_entry(
                    tracker="local-file",
                    issue_id=1,
                    action="branch",
                    applied_at="2026-03-08T01:00:01+00:00",
                    staged_at="20260308T010001000001Z",
                    archived_path=stale_branch,
                    group_key="issue:1|head:reporepublic/old-branch",
                    artifact_role="branch-proposal",
                ),
                _manifest_entry(
                    tracker="local-file",
                    issue_id=1,
                    action="pr-body",
                    applied_at="2026-03-08T01:00:03+00:00",
                    staged_at="20260308T010003000001Z",
                    archived_path=dangling_pr_body,
                    group_key="issue:1|head:reporepublic/old-branch",
                    artifact_role="pr-body-proposal",
                ),
                _manifest_entry(
                    tracker="local-file",
                    issue_id=1,
                    action="comment",
                    applied_at="2026-03-08T01:01:01+00:00",
                    staged_at="20260308T010101000001Z",
                    archived_path=recent_comment,
                    group_key="issue:1|comment",
                    artifact_role="comment-proposal",
                ),
            ],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["clean", "--sync-applied"], catch_exceptions=False)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert "Cleaned 3 stale local paths." in result.stdout
    assert recent_comment.exists()
    assert not stale_branch.exists()
    assert not orphan.exists()
    assert payload == [
        _manifest_entry(
            tracker="local-file",
            issue_id=1,
            action="comment",
            applied_at="2026-03-08T01:01:01+00:00",
            staged_at="20260308T010101000001Z",
            archived_path=recent_comment,
            group_key="issue:1|comment",
            artifact_role="comment-proposal",
        )
    ]


def test_cli_dashboard_writes_html_report(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    store = RunStateStore(demo_repo / ".ai-republic" / "state" / "runs.json")
    artifact_dir = demo_repo / ".ai-republic" / "artifacts" / "issue-1" / "run-dashboard"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_file = artifact_dir / "reviewer.md"
    artifact_file.write_text("# Reviewer\n", encoding="utf-8")
    store.upsert(
        RunRecord(
            run_id="run-dashboard",
            issue_id=1,
            issue_title="Fix empty input crash",
            fingerprint="fp-dashboard",
            status=RunLifecycle.COMPLETED,
            backend_mode="mock",
            summary="Completed run.",
            role_artifacts={"reviewer": str(artifact_file)},
        )
    )
    sync_applied_dir = demo_repo / ".ai-republic" / "sync-applied" / "local-file" / "issue-1"
    sync_applied_dir.mkdir(parents=True, exist_ok=True)
    archived_comment = sync_applied_dir / "20260308T010105000001Z-comment.md"
    archived_comment.write_text(
        "---\nissue_id: 1\nstaged_at: 20260308T010105000001Z\n---\n\nRepoRepublic staged a maintainer note.\n",
        encoding="utf-8",
    )
    (sync_applied_dir / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "entry_key": "local-file:local-file/issue-1/20260308T010105000001Z-comment.md",
                    "tracker": "local-file",
                    "issue_id": 1,
                    "action": "comment",
                    "format": "markdown",
                    "applied_at": "2026-03-08T01:01:05+00:00",
                    "staged_at": "20260308T010105000001Z",
                    "summary": "Comment proposal archived for local sync apply.",
                    "normalized": {
                        "artifact_role": "comment-proposal",
                        "issue_key": "issue:1",
                        "bundle_key": "issue:1|comment",
                        "refs": {},
                        "links": {
                            "self": "local-file/issue-1/20260308T010105000001Z-comment.md",
                        },
                    },
                    "source_relative_path": "local-file/issue-1/20260308T010105000001Z-comment.md",
                    "archived_relative_path": "local-file/issue-1/20260308T010105000001Z-comment.md",
                    "archived_path": str(archived_comment),
                    "effect": "Archived comment handoff.",
                    "handoff": {
                        "group_key": "issue:1|comment",
                        "group_size": 1,
                        "group_index": 0,
                        "group_actions": ["comment"],
                        "related_entry_keys": [
                            "local-file:local-file/issue-1/20260308T010105000001Z-comment.md"
                        ],
                        "related_source_paths": [
                            "local-file/issue-1/20260308T010105000001Z-comment.md"
                        ],
                    },
                }
            ],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["dashboard", "--refresh-seconds", "30", "--format", "all"],
        catch_exceptions=False,
    )

    dashboard_path = demo_repo / ".ai-republic" / "dashboard" / "index.html"
    dashboard_json = demo_repo / ".ai-republic" / "dashboard" / "index.json"
    dashboard_markdown = demo_repo / ".ai-republic" / "dashboard" / "index.md"
    html = dashboard_path.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert "Dashboard exports:" in result.stdout
    assert "- html:" in result.stdout
    assert "- json:" in result.stdout
    assert "- markdown:" in result.stdout
    assert "Included 1 of 1 recorded runs." in result.stdout
    assert dashboard_path.exists()
    assert dashboard_json.exists()
    assert dashboard_markdown.exists()
    assert "Fix empty input crash" in html
    assert "run-dashboard" in html
    assert "Sync handoffs" in html
    assert "comment-proposal" in html
    assert 'data-default-refresh-seconds="30"' in html
    assert 'id="run-search"' in html


def test_cli_sync_ls_lists_staged_artifacts(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-markdown" / "issue-1"
    sync_dir.mkdir(parents=True, exist_ok=True)
    (sync_dir / "20260308T010101000001Z-comment.md").write_text(
        "---\nissue_id: 1\nstaged_at: 20260308T010101000001Z\n---\n\nRepoRepublic staged a maintainer note.\n",
        encoding="utf-8",
    )
    (sync_dir / "20260308T010102000001Z-branch.json").write_text(
        '{\n  "action": "branch",\n  "branch_name": "reporepublic/issue-1-fix",\n  "staged_at": "20260308T010102000001Z"\n}\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["sync", "ls", "--issue", "1"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Sync scope: pending" in result.stdout
    assert "Artifacts: 2" in result.stdout
    assert "state=pending" in result.stdout
    assert "action=branch" in result.stdout
    assert "action=comment" in result.stdout
    assert "local-markdown/issue-1/20260308T010102000001Z-branch.json" in result.stdout


def test_cli_sync_show_renders_selected_artifact(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-markdown" / "issue-1"
    sync_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = sync_dir / "20260308T010101000001Z-comment.md"
    artifact_path.write_text(
        "---\n"
        "issue_id: 1\n"
        "action: post_comment\n"
        "staged_at: 20260308T010101000001Z\n"
        "---\n\n"
        "RepoRepublic staged a maintainer note.\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["sync", "show", "local-markdown/issue-1/20260308T010101000001Z-comment.md"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert f"Path: {artifact_path.resolve()}" in result.stdout
    assert "Action: comment" in result.stdout
    assert "Metadata:" in result.stdout
    assert "action: post_comment" in result.stdout
    assert "Normalized:" in result.stdout
    assert "artifact_role: comment-proposal" in result.stdout
    assert "Body:" in result.stdout
    assert "RepoRepublic staged a maintainer note." in result.stdout


def test_cli_sync_ls_json_includes_normalized_metadata(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-markdown" / "issue-1"
    sync_dir.mkdir(parents=True, exist_ok=True)
    (sync_dir / "20260308T010101000001Z-branch.json").write_text(
        '{\n'
        '  "action": "branch",\n'
        '  "issue_id": 1,\n'
        '  "branch_name": "reporepublic/issue-1-fix",\n'
        '  "base_branch": "main",\n'
        '  "staged_at": "20260308T010101000001Z"\n'
        '}\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["sync", "ls", "--issue", "1", "--format", "json"],
        catch_exceptions=False,
    )

    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert payload[0]["normalized"]["artifact_role"] == "branch-proposal"
    assert payload[0]["normalized"]["refs"]["head"] == "reporepublic/issue-1-fix"
    assert payload[0]["normalized"]["refs"]["base"] == "main"


def test_cli_sync_apply_uses_latest_filtered_artifact_and_lists_applied_scope(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    issue_dir = demo_repo / "issues"
    issue_dir.mkdir(exist_ok=True)
    issue_path = issue_dir / "001-demo.md"
    issue_path.write_text(
        "---\n"
        "id: 1\n"
        "title: Fix empty input crash\n"
        "---\n\n"
        "Return an empty list.\n",
        encoding="utf-8",
    )
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("kind: github", "kind: local_markdown")
        .replace("repo: demo/repo\n", "path: issues\n")
        .replace("mode: fixture\n", ""),
        encoding="utf-8",
    )
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-markdown" / "issue-1"
    sync_dir.mkdir(parents=True, exist_ok=True)
    (sync_dir / "20260308T010101000001Z-comment.md").write_text(
        "---\nissue_id: 1\nstaged_at: 20260308T010101000001Z\n---\n\nOlder note.\n",
        encoding="utf-8",
    )
    (sync_dir / "20260308T010102000001Z-comment.md").write_text(
        "---\nissue_id: 1\nstaged_at: 20260308T010102000001Z\n---\n\nNewest note.\n",
        encoding="utf-8",
    )

    apply_result = runner.invoke(
        app,
        ["sync", "apply", "--issue", "1", "--tracker", "local-markdown", "--action", "comment", "--latest"],
        catch_exceptions=False,
    )
    list_result = runner.invoke(
        app,
        ["sync", "ls", "--scope", "applied", "--issue", "1"],
        catch_exceptions=False,
    )

    assert apply_result.exit_code == 0
    assert "Applied sync artifact:" in apply_result.stdout
    assert "Newest note." in issue_path.read_text(encoding="utf-8")
    assert list_result.exit_code == 0
    assert "state=applied" in list_result.stdout
    assert "20260308T010102000001Z-comment.md" in list_result.stdout


def test_cli_sync_apply_updates_local_file_issue_comments(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    issue_path = demo_repo / "issues.json"
    issue_path.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "id": 1,
                        "number": 1,
                        "title": "Fix empty input crash",
                        "body": "Return an empty list.",
                        "labels": ["bug"],
                        "comments": [],
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("kind: github", "kind: local_file")
        .replace("repo: demo/repo\n", "path: issues.json\n")
        .replace("mode: fixture\n", ""),
        encoding="utf-8",
    )
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-file" / "issue-1"
    sync_dir.mkdir(parents=True, exist_ok=True)
    (sync_dir / "20260308T010106000001Z-comment.md").write_text(
        "---\n"
        "issue_id: 1\n"
        "action: comment\n"
        "staged_at: 20260308T010106000001Z\n"
        "---\n\n"
        "RepoRepublic staged a maintainer note.\n",
        encoding="utf-8",
    )

    apply_result = runner.invoke(
        app,
        ["sync", "apply", "--issue", "1", "--tracker", "local-file", "--action", "comment", "--latest"],
        catch_exceptions=False,
    )
    list_result = runner.invoke(
        app,
        ["sync", "ls", "--scope", "applied", "--issue", "1", "--tracker", "local-file"],
        catch_exceptions=False,
    )
    reloaded = json.loads(issue_path.read_text(encoding="utf-8"))

    assert apply_result.exit_code == 0
    assert "Applied sync artifact:" in apply_result.stdout
    assert reloaded["issues"][0]["comments"][-1]["author"] == "reporepublic"
    assert reloaded["issues"][0]["comments"][-1]["body"] == "RepoRepublic staged a maintainer note."
    assert list_result.exit_code == 0
    assert "state=applied" in list_result.stdout
    assert "local-file/issue-1/20260308T010106000001Z-comment.md" in list_result.stdout


def test_cli_sync_apply_bundle_archives_related_pr_handoff(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    issue_dir = demo_repo / "issues"
    issue_dir.mkdir(exist_ok=True)
    issue_path = issue_dir / "001-demo.md"
    issue_path.write_text(
        "---\n"
        "id: 1\n"
        "title: Fix empty input crash\n"
        "---\n\n"
        "Return an empty list.\n",
        encoding="utf-8",
    )
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("kind: github", "kind: local_markdown")
        .replace("repo: demo/repo\n", "path: issues\n")
        .replace("mode: fixture\n", ""),
        encoding="utf-8",
    )
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-markdown" / "issue-1"
    sync_dir.mkdir(parents=True, exist_ok=True)
    branch_path = sync_dir / "20260308T010201000001Z-branch.json"
    branch_path.write_text(
        '{\n'
        '  "action": "branch",\n'
        '  "issue_id": 1,\n'
        '  "branch_name": "reporepublic/issue-1-fix",\n'
        '  "staged_at": "20260308T010201000001Z"\n'
        '}\n',
        encoding="utf-8",
    )
    pr_path = sync_dir / "20260308T010202000001Z-pr.json"
    pr_path.write_text(
        '{\n'
        '  "action": "pr",\n'
        '  "issue_id": 1,\n'
        '  "title": "RepoRepublic: Fix empty input crash (#1)",\n'
        '  "head_branch": "reporepublic/issue-1-fix",\n'
        '  "base_branch": "main",\n'
        '  "draft": true,\n'
        '  "staged_at": "20260308T010202000001Z"\n'
        '}\n',
        encoding="utf-8",
    )
    (sync_dir / "20260308T010203000001Z-pr-body.md").write_text(
        "---\n"
        "issue_id: 1\n"
        'title: "RepoRepublic: Fix empty input crash (#1)"\n'
        "head_branch: reporepublic/issue-1-fix\n"
        "base_branch: main\n"
        f"metadata_path: {pr_path.resolve()}\n"
        "staged_at: 20260308T010203000001Z\n"
        "---\n\n"
        "Draft PR proposal staged locally.\n",
        encoding="utf-8",
    )

    apply_result = runner.invoke(
        app,
        [
            "sync",
            "apply",
            "--issue",
            "1",
            "--tracker",
            "local-markdown",
            "--action",
            "pr-body",
            "--latest",
            "--bundle",
        ],
        catch_exceptions=False,
    )
    list_result = runner.invoke(
        app,
        ["sync", "ls", "--scope", "applied", "--issue", "1", "--tracker", "local-markdown"],
        catch_exceptions=False,
    )

    assert apply_result.exit_code == 0
    assert "Applied sync bundle:" in apply_result.stdout
    assert "- artifacts: 3" in apply_result.stdout
    assert "- action: branch" in apply_result.stdout
    assert "- action: pr" in apply_result.stdout
    assert "- action: pr-body" in apply_result.stdout
    assert list_result.exit_code == 0
    assert "20260308T010201000001Z-branch.json" in list_result.stdout
    assert "20260308T010202000001Z-pr.json" in list_result.stdout
    assert "20260308T010203000001Z-pr-body.md" in list_result.stdout


def test_cli_retry_forces_immediate_rerun(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    store = RunStateStore(demo_repo / ".ai-republic" / "state" / "runs.json")
    future_retry = utc_now() + timedelta(days=365)
    store.upsert(
        RunRecord(
            run_id="run-3",
            issue_id=1,
            issue_title="Fix empty input crash",
            fingerprint="fp-3",
            status=RunLifecycle.FAILED,
            backend_mode="mock",
            next_retry_at=future_retry,
        )
    )

    result = runner.invoke(app, ["retry", "1"], catch_exceptions=False)

    reloaded = RunStateStore(demo_repo / ".ai-republic" / "state" / "runs.json")
    record = reloaded.get(1)
    assert result.exit_code == 0
    assert "scheduled for immediate retry" in result.stdout
    assert record is not None
    assert record.status == RunLifecycle.RETRY_PENDING
    assert record.next_retry_at is not None
    assert record.next_retry_at < future_retry
    assert record.last_error == "Manual retry requested from CLI."


def test_cli_clean_removes_terminal_run_workspace_and_artifacts(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    workspace = demo_repo / ".ai-republic" / "workspaces" / "issue-1" / "run-4" / "repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# stale workspace\n", encoding="utf-8")
    artifact_dir = demo_repo / ".ai-republic" / "artifacts" / "issue-1" / "run-4"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_file = artifact_dir / "reviewer.md"
    artifact_file.write_text("stale artifact\n", encoding="utf-8")

    store = RunStateStore(demo_repo / ".ai-republic" / "state" / "runs.json")
    store.upsert(
        RunRecord(
            run_id="run-4",
            issue_id=1,
            issue_title="Fix empty input crash",
            fingerprint="fp-4",
            status=RunLifecycle.COMPLETED,
            backend_mode="mock",
            workspace_path=str(workspace),
            role_artifacts={"reviewer": str(artifact_file)},
        )
    )

    result = runner.invoke(app, ["clean"], catch_exceptions=False)

    reloaded = RunStateStore(demo_repo / ".ai-republic" / "state" / "runs.json")
    record = reloaded.get(1)
    assert result.exit_code == 0
    assert "Cleaned 2 stale local paths." in result.stdout
    assert not workspace.exists()
    assert not artifact_dir.exists()
    assert record is not None
    assert record.workspace_path is None
    assert record.role_artifacts == {}


def test_cli_clean_dry_run_lists_actions_without_deleting(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    orphan_workspace = demo_repo / ".ai-republic" / "workspaces" / "issue-9" / "run-old" / "repo"
    orphan_workspace.mkdir(parents=True, exist_ok=True)
    (orphan_workspace / "README.md").write_text("# orphan workspace\n", encoding="utf-8")

    result = runner.invoke(app, ["clean", "--dry-run"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Clean preview:" in result.stdout
    assert "workspace-orphan:" in result.stdout
    assert orphan_workspace.exists()


def test_cli_run_writes_jsonl_file_logs_when_enabled(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("file_enabled: false", "file_enabled: true"),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["run", "--once"], catch_exceptions=False)

    log_path = demo_repo / ".ai-republic" / "logs" / "reporepublic.jsonl"
    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert result.exit_code == 0
    assert log_path.exists()
    assert any(entry["message"] == "Issue run started." and entry["issue_id"] == 1 for entry in lines)
    assert any(entry["message"] == "Role completed." and entry["role"] == "reviewer" for entry in lines)
    assert any(entry["message"] == "Issue run completed." and "run_id" in entry for entry in lines)


def test_cli_doctor_reports_drift_and_hints(demo_git_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_git_repo)
    config_path = demo_git_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("mode: fixture", "mode: rest"),
        encoding="utf-8",
    )
    (demo_git_repo / ".ai-republic" / "roles" / "triage.md").write_text(
        "custom drift\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")
    monkeypatch.setattr(
        app_module,
        "_probe_github_auth",
        lambda loaded: app_module.DiagnosticCheck(
            name="GitHub auth",
            status="WARN",
            message="GITHUB_TOKEN is not set",
            hint="Set GITHUB_TOKEN or run `gh auth login`.",
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_probe_github_network",
        lambda loaded: app_module.DiagnosticCheck(
            name="GitHub network",
            status="WARN",
            message="could not reach https://api.github.com/rate_limit",
            hint="Check network connectivity.",
        ),
    )

    result = runner.invoke(app, ["doctor"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "GitHub auth: WARN (GITHUB_TOKEN is not set)" in result.stdout
    assert "hint: Set GITHUB_TOKEN or run `gh auth login`." in result.stdout
    assert "GitHub network: WARN (could not reach https://api.github.com/rate_limit)" in result.stdout
    assert "Template drift: WARN (" in result.stdout
    assert "triage.md" in result.stdout


def test_cli_doctor_reports_local_file_tracker_status(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("kind: github", "kind: local_file")
        .replace("repo: demo/repo\n", "path: issues.json\n")
        .replace("mode: fixture\n", ""),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")

    result = runner.invoke(app, ["doctor"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Tracker: kind=local_file" in result.stdout
    assert "Local tracker file: OK" in result.stdout


def test_cli_doctor_reports_local_markdown_tracker_status(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
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

    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")

    result = runner.invoke(app, ["doctor"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Tracker: kind=local_markdown" in result.stdout
    assert "Local tracker directory: OK" in result.stdout


def _configure_sync_retention(repo_root: Path, *, keep_groups: int) -> None:
    config_path = repo_root / ".ai-republic" / "reporepublic.yaml"
    payload = load_config(repo_root).data.model_dump(mode="json")
    payload.setdefault("cleanup", {})["sync_applied_keep_groups_per_issue"] = keep_groups
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _manifest_entry(
    *,
    tracker: str,
    issue_id: int,
    action: str,
    applied_at: str,
    staged_at: str,
    archived_path: Path,
    group_key: str,
    artifact_role: str,
) -> dict[str, object]:
    archived_relative_path = "/".join(archived_path.parts[-3:])
    relative_source_path = archived_relative_path
    return {
        "entry_key": f"{tracker}:{relative_source_path}",
        "tracker": tracker,
        "issue_id": issue_id,
        "action": action,
        "format": "markdown" if archived_path.suffix == ".md" else "json",
        "applied_at": applied_at,
        "staged_at": staged_at,
        "summary": f"{action} handoff.",
        "normalized": {
            "artifact_role": artifact_role,
            "issue_key": f"issue:{issue_id}",
            "bundle_key": group_key,
            "refs": {},
            "links": {
                "self": relative_source_path,
            },
        },
        "source_relative_path": relative_source_path,
        "archived_relative_path": archived_relative_path,
        "archived_path": str(archived_path),
        "effect": f"Archived {action} handoff.",
        "handoff": {
            "group_key": group_key,
            "group_size": 1,
            "group_index": 0,
            "group_actions": [action],
            "related_entry_keys": [f"{tracker}:{relative_source_path}"],
            "related_source_paths": [relative_source_path],
        },
    }
