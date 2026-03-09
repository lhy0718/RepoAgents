from __future__ import annotations

import importlib
import json
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner
import yaml

from reporepublic.cli.app import app
from reporepublic.config import load_config
from reporepublic.models import ExternalActionResult, IssueComment, IssueRef, RunLifecycle, RunRecord
from reporepublic.models.domain import utc_now
from reporepublic.orchestrator import RunStateStore
from reporepublic.sync_audit import SyncAuditBuildResult


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


def test_cli_status_includes_report_health_summary(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(
        "reporepublic.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
    _write_dashboard_reports(demo_repo)
    _write_ops_snapshot_index(demo_repo)
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

    result = runner.invoke(app, ["status"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Run summary: completed=1" in result.stdout
    assert "Report health: severity=issues title=Report freshness needs action reports=2" in result.stdout
    assert "policy: unknown>=1 stale>=1 future>=1 aging>=1" in result.stdout
    assert (
        "policy_health: clean | thresholds unknown>=1 stale>=1 future>=1 aging>=1"
    ) in result.stdout
    assert (
        "overall: issues | fresh 0 · aging 1 · stale 1 / 2 total | "
        "stale reports need regeneration or operator review"
    ) in result.stdout
    assert (
        "cleanup: issues | fresh 0 · aging 0 · stale 1 / 1 total | "
        "stale reports need regeneration or operator review"
    ) in result.stdout
    assert "Ops snapshots: status=available entries=2/5 archives=1 dropped=1" in result.stdout
    assert "latest: 20260309T101500Z | clean | age=" in result.stdout
    assert f"bundle: {demo_repo / '.ai-republic' / 'reports' / 'ops' / '20260309T101500Z'}" in result.stdout


def test_cli_status_warns_on_report_policy_export_mismatch(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(
        "reporepublic.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    unknown_issues_threshold: 2",
                "    stale_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_dashboard_reports(demo_repo)
    report_json = demo_repo / ".ai-republic" / "reports" / "sync-audit.json"
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    payload["policy"] = {
        "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
        "report_freshness_policy": {
            "unknown_issues_threshold": 1,
            "stale_issues_threshold": 1,
            "future_attention_threshold": 1,
            "aging_attention_threshold": 1,
        },
    }
    report_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

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

    result = runner.invoke(app, ["status"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "policy: unknown>=2 stale>=2 future>=2 aging>=2" in result.stdout
    assert (
        "policy_health: attention | thresholds unknown>=2 stale>=2 future>=2 aging>=2; "
        "1 raw report export uses a different embedded policy"
    ) in result.stdout
    assert (
        "policy_warning: 1 raw report exports use a different embedded policy"
    ) in result.stdout
    assert (
        "  related report details:"
    ) in result.stdout
    assert (
        "    policy_drifts:"
    ) in result.stdout
    assert (
        "      - sync-audit.json embedded=unknown>=1 stale>=1 future>=1 aging>=1 "
        "current=unknown>=2 stale>=2 future>=2 aging>=2"
    ) in result.stdout
    assert (
        "    remediation: refresh raw report exports to align embedded policy metadata; "
        "re-run `republic sync audit --format all` and `republic clean --report "
        "--report-format all` after updating `dashboard.report_freshness_policy`"
    ) in result.stdout


def test_cli_status_exports_json_and_markdown(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    _write_ops_snapshot_index(demo_repo)
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

    result = runner.invoke(app, ["status", "--format", "all"], catch_exceptions=False)

    report_json = demo_repo / ".ai-republic" / "reports" / "status.json"
    report_markdown = demo_repo / ".ai-republic" / "reports" / "status.md"
    payload = json.loads(report_json.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert "Status exports:" in result.stdout
    assert "Status summary: selected_runs=1 total_runs=1" in result.stdout
    assert report_json.exists()
    assert report_markdown.exists()
    assert payload["summary"]["total_runs"] == 1
    assert payload["summary"]["selected_runs"] == 1
    assert payload["runs"][0]["issue_id"] == 1
    assert payload["report_health"]["policy_health"]["severity"] == "clean"
    assert payload["ops_snapshots"]["latest"]["entry_id"] == "20260309T101500Z"
    markdown = report_markdown.read_text(encoding="utf-8")
    assert "# Status report" in markdown
    assert "## Ops snapshots" in markdown
    assert "- history_entry_count: 2" in markdown


def test_cli_status_exports_filtered_issue_to_custom_path(demo_repo: Path, monkeypatch) -> None:
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
        )
    )
    store.upsert(
        RunRecord(
            run_id="run-2",
            issue_id=2,
            issue_title="Improve README quickstart",
            fingerprint="fp-2",
            status=RunLifecycle.FAILED,
            backend_mode="mock",
        )
    )

    output = demo_repo / "tmp" / "ops-status.out"
    result = runner.invoke(
        app,
        ["status", "--issue", "2", "--format", "json", "--output", str(output)],
        catch_exceptions=False,
    )

    payload = json.loads((demo_repo / "tmp" / "ops-status.json").read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert payload["meta"]["issue_filter"] == 2
    assert payload["summary"]["total_runs"] == 2
    assert payload["summary"]["selected_runs"] == 1
    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["issue_id"] == 2


def test_cli_ops_snapshot_exports_bundle(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")
    monkeypatch.setattr(
        "reporepublic.ops_status.utc_now",
        lambda: datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )

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

    output_dir = demo_repo / "tmp" / "ops-bundle"
    result = runner.invoke(
        app,
        ["ops", "snapshot", "--output-dir", str(output_dir), "--dashboard-limit", "10", "--sync-limit", "10"],
        catch_exceptions=False,
    )

    manifest_json = output_dir / "bundle.json"
    manifest_markdown = output_dir / "bundle.md"
    bundle_ops_status_json = output_dir / "ops-status.json"
    bundle_ops_status_markdown = output_dir / "ops-status.md"
    bundle_sync_health_json = output_dir / "sync-health.json"
    bundle_sync_health_markdown = output_dir / "sync-health.md"
    ops_status_json = demo_repo / ".ai-republic" / "reports" / "ops-status.json"
    ops_status_markdown = demo_repo / ".ai-republic" / "reports" / "ops-status.md"
    sync_health_json = demo_repo / ".ai-republic" / "reports" / "sync-health.json"
    sync_health_markdown = demo_repo / ".ai-republic" / "reports" / "sync-health.md"
    payload = json.loads(manifest_json.read_text(encoding="utf-8"))
    ops_status_payload = json.loads(ops_status_json.read_text(encoding="utf-8"))
    sync_health_payload = json.loads(sync_health_json.read_text(encoding="utf-8"))
    bundle_pairs = {(entry["source"], entry["target"]) for entry in payload["cross_links"]}

    assert result.exit_code == 0
    assert "Ops snapshot bundle:" in result.stdout
    assert f"- bundle_dir: {output_dir}" in result.stdout
    assert f"- bundle_sync_health_json: {bundle_sync_health_json}" in result.stdout
    assert f"- bundle_sync_health_markdown: {bundle_sync_health_markdown}" in result.stdout
    assert f"- root_sync_health_json: {sync_health_json}" in result.stdout
    assert f"- root_sync_health_markdown: {sync_health_markdown}" in result.stdout
    assert f"- ops_status_json: {bundle_ops_status_json}" in result.stdout
    assert f"- ops_status_markdown: {bundle_ops_status_markdown}" in result.stdout
    assert f"- root_ops_status_json: {ops_status_json}" in result.stdout
    assert f"- root_ops_status_markdown: {ops_status_markdown}" in result.stdout
    assert manifest_json.exists()
    assert manifest_markdown.exists()
    assert bundle_sync_health_json.exists()
    assert bundle_sync_health_markdown.exists()
    assert bundle_ops_status_json.exists()
    assert bundle_ops_status_markdown.exists()
    assert sync_health_json.exists()
    assert sync_health_markdown.exists()
    assert ops_status_json.exists()
    assert ops_status_markdown.exists()
    assert payload["summary"]["overall_status"] == "clean"
    assert payload["components"]["doctor"]["status"] == "clean"
    assert payload["components"]["status"]["selected_runs"] == 1
    assert payload["components"]["dashboard"]["output_paths"]["html"].endswith("dashboard.html")
    assert payload["components"]["sync_audit"]["status"] == "clean"
    assert payload["components"]["sync_health"]["output_paths"]["json"].endswith("sync-health.json")
    assert payload["components"]["sync_health"]["next_action_count"] == 0
    assert payload["components"]["ops_status"]["output_paths"]["json"].endswith("ops-status.json")
    assert payload["components"]["ops_status"]["related_report_count"] == 2
    assert ("sync_health", "sync_audit") in bundle_pairs
    assert ("sync_audit", "sync_health") in bundle_pairs
    assert ("ops_status", "sync_audit") in bundle_pairs
    assert ("sync_audit", "ops_status") in bundle_pairs
    assert sync_health_payload["summary"]["pending_artifacts"] == 0
    assert sync_health_payload["summary"]["next_actions"] == []
    assert ops_status_payload["latest"]["entry_id"] == output_dir.name
    assert ops_status_payload["latest_bundle"]["component_count"] == 6
    assert ops_status_payload["related_reports"]["entries"][0]["key"] == "sync-audit"
    assert ops_status_payload["related_reports"]["entries"][1]["key"] == "sync-health"


def test_cli_ops_snapshot_returns_non_zero_when_sync_audit_has_issues(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")

    def _fake_sync_audit_report(
        loaded,
        *,
        output_path,
        formats,
        issue_id,
        tracker,
        limit,
    ):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "meta": {"rendered_at": "2026-03-09T00:00:00+00:00"},
                    "summary": {"overall_status": "issues"},
                }
            ),
            encoding="utf-8",
        )
        output_path.with_suffix(".md").write_text("# Sync audit\n", encoding="utf-8")
        return SyncAuditBuildResult(
            output_paths={"json": output_path, "markdown": output_path.with_suffix(".md")},
            overall_status="issues",
            pending_artifacts=0,
            integrity_issue_count=2,
            prunable_groups=0,
            related_cleanup_reports=0,
            cleanup_report_mismatches=0,
            cleanup_mismatch_warnings=(),
            related_cleanup_policy_drifts=0,
            cleanup_policy_drift_warnings=(),
            policy_drift_guidance=None,
        )

    monkeypatch.setattr(app_module, "build_sync_audit_report", _fake_sync_audit_report)

    output_dir = demo_repo / "tmp" / "ops-bundle-issues"
    result = runner.invoke(
        app,
        ["ops", "snapshot", "--output-dir", str(output_dir), "--issue", "1"],
        catch_exceptions=False,
    )

    payload = json.loads((output_dir / "bundle.json").read_text(encoding="utf-8"))
    assert result.exit_code == 1
    assert payload["summary"]["overall_status"] == "issues"
    assert payload["components"]["sync_audit"]["status"] == "issues"


def test_cli_ops_snapshot_can_include_cleanup_preview_and_existing_result(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")

    reports_dir = demo_repo / ".ai-republic" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "cleanup-result.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-09T00:00:00+00:00", "mode": "applied"},
                "summary": {
                    "overall_status": "cleaned",
                    "action_count": 2,
                    "related_sync_audit_reports": 1,
                    "sync_audit_policy_drifts": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "cleanup-result.md").write_text("# Cleanup result\n", encoding="utf-8")

    output_dir = demo_repo / "tmp" / "ops-bundle-with-cleanup"
    result = runner.invoke(
        app,
        [
            "ops",
            "snapshot",
            "--output-dir",
            str(output_dir),
            "--include-cleanup-preview",
            "--include-cleanup-result",
        ],
        catch_exceptions=False,
    )

    payload = json.loads((output_dir / "bundle.json").read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert (output_dir / "cleanup-preview.json").exists()
    assert (output_dir / "cleanup-preview.md").exists()
    assert (output_dir / "cleanup-result.json").exists()
    assert (output_dir / "cleanup-result.md").exists()
    assert payload["components"]["cleanup_preview"]["status"] in {"clean", "attention"}
    assert payload["components"]["cleanup_result"]["status"] == "clean"
    assert payload["components"]["cleanup_result"]["action_count"] == 2
    assert any(
        entry["source"] == "sync_audit" and entry["target"] == "cleanup_preview"
        for entry in payload["cross_links"]
    )
    assert any(
        entry["source"] == "sync_audit" and entry["target"] == "cleanup_result"
        for entry in payload["cross_links"]
    )


def test_cli_ops_snapshot_can_include_sync_check_and_repair_preview(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")

    applied_root = demo_repo / ".ai-republic" / "sync-applied" / "local-file" / "issue-1"
    applied_root.mkdir(parents=True, exist_ok=True)
    (applied_root / "20260308T010105000001Z-comment.md").write_text(
        "---\nissue_id: 1\n---\n\nOrphan handoff.\n",
        encoding="utf-8",
    )

    output_dir = demo_repo / "tmp" / "ops-bundle-with-sync-components"
    result = runner.invoke(
        app,
        [
            "ops",
            "snapshot",
            "--output-dir",
            str(output_dir),
            "--issue",
            "1",
            "--include-sync-check",
            "--include-sync-repair-preview",
        ],
        catch_exceptions=False,
    )

    payload = json.loads((output_dir / "bundle.json").read_text(encoding="utf-8"))
    pairs = {(entry["source"], entry["target"]) for entry in payload["cross_links"]}

    assert result.exit_code == 1
    assert (output_dir / "sync-check.json").exists()
    assert (output_dir / "sync-check.md").exists()
    assert (output_dir / "sync-repair-preview.json").exists()
    assert (output_dir / "sync-repair-preview.md").exists()
    assert payload["components"]["sync_check"]["status"] == "issues"
    assert payload["components"]["sync_check"]["issues_with_findings"] == 1
    assert payload["components"]["sync_repair_preview"]["status"] == "attention"
    assert payload["components"]["sync_repair_preview"]["changed_reports"] == 1
    assert payload["components"]["sync_repair_preview"]["adopted_archives"] == 1
    assert ("sync_audit", "sync_check") in pairs
    assert ("sync_check", "sync_repair_preview") in pairs
    assert ("sync_repair_preview", "sync_check") in pairs
    assert len(payload["cross_links"]) == len(pairs)


def test_cli_ops_snapshot_can_write_archive_handoff(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")

    output_dir = demo_repo / "tmp" / "ops-bundle-archive"
    archive_path = demo_repo / "tmp" / "handoff.tar.gz"
    ops_index_root = demo_repo / ".ai-republic" / "reports" / "ops"
    result = runner.invoke(
        app,
        [
            "ops",
            "snapshot",
            "--output-dir",
            str(output_dir),
            "--archive",
            "--archive-output",
            str(archive_path),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert archive_path.exists()
    assert f"- archive_path: {archive_path}" in result.stdout
    assert f"- latest_index_json: {ops_index_root / 'latest.json'}" in result.stdout
    assert f"- history_index_json: {ops_index_root / 'history.json'}" in result.stdout
    assert "- archive_sha256: " in result.stdout
    assert "- archive_file_count: " in result.stdout
    latest_payload = json.loads((ops_index_root / "latest.json").read_text(encoding="utf-8"))
    history_payload = json.loads((ops_index_root / "history.json").read_text(encoding="utf-8"))
    assert latest_payload["latest"]["bundle_dir"] == str(output_dir)
    assert latest_payload["latest"]["archive"]["path"] == str(archive_path)
    assert history_payload["latest_entry_id"] == output_dir.name
    with tarfile.open(archive_path, "r:gz") as bundle_archive:
        members = bundle_archive.getnames()
    assert f"{output_dir.name}/bundle.json" in members
    assert f"{output_dir.name}/doctor.json" in members


def test_cli_ops_status_prints_latest_history_and_bundle_manifest(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(
        "reporepublic.ops_status.utc_now",
        lambda: datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )
    _write_ops_snapshot_index(demo_repo)

    result = runner.invoke(app, ["ops", "status", "--limit", "2"], catch_exceptions=False)

    assert result.exit_code == 0
    assert (
        "Ops snapshot status: status=clean index=available entries=2/5 archives=1 dropped=1"
        in result.stdout
    )
    assert "Latest index entry: 20260309T101500Z overall=clean age=1h 45m" in result.stdout
    assert (
        "Latest bundle manifest: status=available overall=clean components=4 cross_links=2"
        in result.stdout
    )
    assert "  manifest: " in result.stdout
    assert "  - doctor: clean | diagnostic_count=5, exit_code=0" in result.stdout
    assert (
        "  - dashboard: clean | available_reports=3, report_health_severity=attention, "
        "total_runs=4, visible_runs=4"
    ) in result.stdout
    assert "History preview:" in result.stdout
    assert "  - 20260309T100000Z | issues | age=2h 0m | archive=no" in result.stdout


def test_cli_ops_status_exports_json_and_markdown(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(
        "reporepublic.ops_status.utc_now",
        lambda: datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )
    _write_ops_snapshot_index(demo_repo)

    result = runner.invoke(app, ["ops", "status", "--format", "all"], catch_exceptions=False)

    report_json = demo_repo / ".ai-republic" / "reports" / "ops-status.json"
    report_markdown = demo_repo / ".ai-republic" / "reports" / "ops-status.md"
    payload = json.loads(report_json.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert "Ops status exports:" in result.stdout
    assert "Ops status summary: status=clean index=available latest_bundle=available" in result.stdout
    assert report_json.exists()
    assert report_markdown.exists()
    assert payload["summary"]["status"] == "clean"
    assert payload["summary"]["history_entry_count"] == 2
    assert payload["latest"]["entry_id"] == "20260309T101500Z"
    assert payload["latest_bundle"]["status"] == "available"
    assert payload["latest_bundle"]["component_count"] == 4
    assert payload["latest_bundle"]["cross_link_count"] == 2
    assert payload["latest_bundle"]["components"][0]["key"] == "dashboard"
    markdown = report_markdown.read_text(encoding="utf-8")
    assert "# Ops snapshot status" in markdown
    assert "## Latest bundle manifest" in markdown
    assert "## History preview" in markdown


def test_cli_github_smoke_exports_json_and_markdown(
    demo_git_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_git_repo)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    config_path = demo_git_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("mode: fixture", "mode: rest"),
        encoding="utf-8",
    )

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
                            {"author": "demo", "body": "please fix"}
                        )
                    ],
                }
            )

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(app_module, "build_tracker", lambda loaded, dry_run=False: FakeTracker())

    result = runner.invoke(
        app,
        ["github", "smoke", "--issue", "1", "--format", "all"],
        catch_exceptions=False,
    )

    report_json = demo_git_repo / ".ai-republic" / "reports" / "github-smoke.json"
    report_markdown = demo_git_repo / ".ai-republic" / "reports" / "github-smoke.md"
    payload = json.loads(report_json.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert "GitHub smoke exports:" in result.stdout
    assert "GitHub smoke summary: status=clean open_issues=1 sampled_issue=1" in result.stdout
    assert report_json.exists()
    assert report_markdown.exists()
    assert payload["summary"]["status"] == "clean"
    assert payload["repo_access"]["full_name"] == "demo/repo"
    assert payload["sampled_issue"]["comment_count"] == 1
    assert "# GitHub smoke report" in report_markdown.read_text(encoding="utf-8")


def test_cli_github_smoke_requires_write_ready_when_requested(
    demo_git_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_git_repo)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    config_path = demo_git_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("mode: fixture", "mode: rest")
        .replace("allow_open_pr: false", "allow_open_pr: true"),
        encoding="utf-8",
    )

    class FakeTracker:
        async def get_repo_info(self) -> dict[str, object]:
            return {"full_name": "demo/repo", "default_branch": "main", "private": False}

        async def list_open_issues(self) -> list[IssueRef]:
            return []

        async def get_issue(self, issue_id: int) -> IssueRef:
            raise AssertionError("get_issue should not be called")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(app_module, "build_tracker", lambda loaded, dry_run=False: FakeTracker())

    result = runner.invoke(
        app,
        ["github", "smoke", "--require-write-ready"],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "publish readiness: warn" in result.stdout.lower()


def test_cli_ops_snapshot_can_prune_managed_history_entries(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")

    ops_index_root = demo_repo / ".ai-republic" / "reports" / "ops"
    old_output_dir = ops_index_root / "20260309T090000Z"
    old_output_dir.mkdir(parents=True, exist_ok=True)
    (old_output_dir / "bundle.json").write_text("{}\n", encoding="utf-8")
    (old_output_dir / "bundle.md").write_text("# Bundle\n", encoding="utf-8")
    old_archive_path = ops_index_root / "20260309T090000Z.tar.gz"
    old_archive_path.write_text("archive\n", encoding="utf-8")
    (ops_index_root / "history.json").write_text(
        json.dumps(
            {
                "meta": {
                    "generated_at": "2026-03-09T09:00:00+00:00",
                    "ops_root": str(ops_index_root),
                    "history_limit": 2,
                    "entry_count": 1,
                    "dropped_entry_count": 0,
                },
                "latest_entry_id": "20260309T090000Z",
                "entries": [
                    {
                        "entry_id": "20260309T090000Z",
                        "rendered_at": "2026-03-09T09:00:00+00:00",
                        "overall_status": "clean",
                        "bundle_dir": str(old_output_dir),
                        "bundle_relative_dir": "20260309T090000Z",
                        "bundle_json": str(old_output_dir / "bundle.json"),
                        "bundle_markdown": str(old_output_dir / "bundle.md"),
                        "archive": {
                            "path": str(old_archive_path),
                            "relative_path": "20260309T090000Z.tar.gz",
                            "sha256": "x" * 64,
                            "size_bytes": old_archive_path.stat().st_size,
                            "file_count": 2,
                            "member_count": 3,
                        },
                        "component_statuses": {"doctor": "clean"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _configure_ops_snapshot_retention(demo_repo, keep_entries=1, prune_managed=True)

    output_dir = demo_repo / "tmp" / "ops-bundle-pruned"
    result = runner.invoke(
        app,
        [
            "ops",
            "snapshot",
            "--output-dir",
            str(output_dir),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert not old_output_dir.exists()
    assert not old_archive_path.exists()
    assert "- history_limit: 1" in result.stdout
    assert "- dropped_history_entries: 1" in result.stdout
    assert "- prune_history: true" in result.stdout
    assert "- pruned_bundle_dirs: 1" in result.stdout
    assert "- pruned_archives: 1" in result.stdout
    latest_payload = json.loads((ops_index_root / "latest.json").read_text(encoding="utf-8"))
    history_payload = json.loads((ops_index_root / "history.json").read_text(encoding="utf-8"))
    assert latest_payload["meta"]["history_limit"] == 1
    assert latest_payload["meta"]["dropped_entry_count"] == 1
    assert history_payload["meta"]["history_limit"] == 1
    assert history_payload["meta"]["dropped_entry_count"] == 1
    assert [entry["entry_id"] for entry in history_payload["entries"]] == [output_dir.name]


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


def test_cli_clean_sync_applied_dry_run_writes_cleanup_report(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    _configure_sync_retention(demo_repo, keep_groups=1)
    sync_issue_root = demo_repo / ".ai-republic" / "sync-applied" / "local-file" / "issue-1"
    sync_issue_root.mkdir(parents=True, exist_ok=True)
    stale_branch = sync_issue_root / "20260308T010001000001Z-branch.json"
    recent_comment = sync_issue_root / "20260308T010101000001Z-comment.md"
    stale_branch.write_text('{"action":"branch","issue_id":1}\n', encoding="utf-8")
    recent_comment.write_text("---\nissue_id: 1\n---\n\nRecent comment handoff.\n", encoding="utf-8")
    (sync_issue_root / "manifest.json").write_text(
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

    result = runner.invoke(
        app,
        ["clean", "--sync-applied", "--dry-run", "--report", "--report-format", "all"],
        catch_exceptions=False,
    )
    report_json = demo_repo / ".ai-republic" / "reports" / "cleanup-preview.json"
    report_markdown = demo_repo / ".ai-republic" / "reports" / "cleanup-preview.md"
    payload = json.loads(report_json.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert "Cleanup report exports:" in result.stdout
    assert "Cleanup report summary: mode=preview" in result.stdout
    assert report_json.exists()
    assert report_markdown.exists()
    assert payload["meta"]["mode"] == "preview"
    assert payload["policy"]["summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert payload["summary"]["action_count"] >= 1
    assert payload["summary"]["sync_applied_action_count"] >= 1
    assert payload["summary"]["related_sync_audit_reports"] == 0
    assert payload["summary"]["sync_audit_policy_drifts"] == 0
    assert payload["actions"][0]["kind"].startswith("sync-applied")


def test_cli_clean_report_surfaces_sync_audit_policy_drift(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    unknown_issues_threshold: 2",
                "    stale_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    reports_dir = demo_repo / ".ai-republic" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "sync-audit.json").write_text(
        json.dumps(
            {
                "meta": {
                    "rendered_at": "2026-03-08T05:00:00+00:00",
                    "issue_filter": 1,
                },
                "policy": {
                    "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
                    "report_freshness_policy": {
                        "unknown_issues_threshold": 1,
                        "stale_issues_threshold": 1,
                        "future_attention_threshold": 1,
                        "aging_attention_threshold": 1,
                    },
                },
                "summary": {
                    "overall_status": "attention",
                    "pending_artifacts": 1,
                    "integrity_issue_count": 0,
                    "prunable_groups": 1,
                    "repair_needed_issues": 0,
                    "cleanup_report_mismatches": 0,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "sync-audit.md").write_text("# Sync audit\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["clean", "--dry-run", "--report", "--report-format", "all", "--show-remediation"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Cleanup report summary: mode=preview" in result.stdout
    assert "Related sync audit reports: 1" in result.stdout
    assert "Sync audit policy drifts: 1" in result.stdout
    assert "Related sync audit details:" in result.stdout
    assert "  policy_drifts:" in result.stdout
    assert (
        "    - Sync audit: embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)"
    ) in result.stdout
    assert (
        "  remediation: refresh raw report exports to align embedded policy metadata; "
        "re-run `republic sync audit --format all` and `republic clean --report "
        "--report-format all` after updating `dashboard.report_freshness_policy`"
    ) in result.stdout


def test_cli_clean_report_can_print_sync_audit_mismatch_details(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    sync_issue_root = demo_repo / ".ai-republic" / "sync-applied" / "local-file" / "issue-7"
    sync_issue_root.mkdir(parents=True, exist_ok=True)
    reports_dir = demo_repo / ".ai-republic" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "sync-audit.json").write_text(
        json.dumps(
            {
                "meta": {
                    "rendered_at": "2026-03-08T05:00:00+00:00",
                    "issue_filter": 1,
                },
                "policy": {
                    "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
                    "report_freshness_policy": {
                        "unknown_issues_threshold": 1,
                        "stale_issues_threshold": 1,
                        "future_attention_threshold": 1,
                        "aging_attention_threshold": 1,
                    },
                },
                "summary": {
                    "overall_status": "attention",
                    "pending_artifacts": 1,
                    "integrity_issue_count": 0,
                    "prunable_groups": 1,
                    "repair_needed_issues": 0,
                    "cleanup_report_mismatches": 0,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "sync-audit.md").write_text("# Sync audit\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["clean", "--issue", "7", "--sync-applied", "--dry-run", "--report", "--show-mismatches"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Sync audit issue filter mismatches: 1" in result.stdout
    assert "Related sync audit details:" in result.stdout
    assert "  mismatches:" in result.stdout
    assert (
        "    - Sync audit: sync audit issue_filter=1 does not match cleanup issue_filter=7"
        in result.stdout
    )


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


def test_cli_clean_sync_applied_writes_cleanup_result_report(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    _configure_sync_retention(demo_repo, keep_groups=1)
    sync_issue_root = demo_repo / ".ai-republic" / "sync-applied" / "local-file" / "issue-2"
    sync_issue_root.mkdir(parents=True, exist_ok=True)
    orphan = sync_issue_root / "20260308T005959000001Z-orphan.md"
    orphan.write_text("orphan\n", encoding="utf-8")
    manifest_path = sync_issue_root / "manifest.json"
    manifest_path.write_text("[]\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["clean", "--sync-applied", "--issue", "2", "--report"],
        catch_exceptions=False,
    )
    report_json = demo_repo / ".ai-republic" / "reports" / "cleanup-result.json"
    payload = json.loads(report_json.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert "Cleanup report exports:" in result.stdout
    assert report_json.exists()
    assert payload["meta"]["mode"] == "applied"
    assert payload["policy"]["report_freshness_policy"]["stale_issues_threshold"] == 1
    assert payload["summary"]["action_count"] >= 1
    assert payload["summary"]["overall_status"] == "cleaned"
    assert any(action["kind"] == "sync-applied-issue-root" for action in payload["actions"])


def test_cli_dashboard_writes_html_report(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    _configure_sync_retention(demo_repo, keep_groups=1)
    _write_dashboard_reports(demo_repo)
    monkeypatch.setattr(
        "reporepublic.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
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
    archived_branch = sync_applied_dir / "20260308T010001000001Z-branch.json"
    archived_branch.write_text(
        json.dumps(
            {
                "action": "branch",
                "issue_id": 1,
                "branch_name": "reporepublic/issue-1-older",
                "base_branch": "main",
                "staged_at": "20260308T010001000001Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    archived_comment.write_text(
        "---\nissue_id: 1\nstaged_at: 20260308T010105000001Z\n---\n\nRepoRepublic staged a maintainer note.\n",
        encoding="utf-8",
    )
    (sync_applied_dir / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "entry_key": "local-file:local-file/issue-1/20260308T010001000001Z-branch.json",
                    "tracker": "local-file",
                    "issue_id": 1,
                    "action": "branch",
                    "format": "json",
                    "applied_at": "2026-03-08T01:00:01+00:00",
                    "staged_at": "20260308T010001000001Z",
                    "summary": "Older branch proposal archived for cleanup.",
                    "normalized": {
                        "artifact_role": "branch-proposal",
                        "issue_key": "issue:1",
                        "bundle_key": "issue:1|head:reporepublic/issue-1-older",
                        "refs": {
                            "head": "reporepublic/issue-1-older",
                            "base": "main",
                        },
                        "links": {
                            "self": "local-file/issue-1/20260308T010001000001Z-branch.json",
                        },
                    },
                    "source_relative_path": "local-file/issue-1/20260308T010001000001Z-branch.json",
                    "archived_relative_path": "local-file/issue-1/20260308T010001000001Z-branch.json",
                    "archived_path": str(archived_branch),
                    "effect": "Archived branch handoff.",
                    "handoff": {
                        "group_key": "issue:1|head:reporepublic/issue-1-older",
                        "group_size": 1,
                        "group_index": 0,
                        "group_actions": ["branch"],
                        "related_entry_keys": [
                            "local-file:local-file/issue-1/20260308T010001000001Z-branch.json"
                        ],
                        "related_source_paths": [
                            "local-file/issue-1/20260308T010001000001Z-branch.json"
                        ],
                    },
                },
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
    payload = json.loads(dashboard_json.read_text(encoding="utf-8"))
    markdown = dashboard_markdown.read_text(encoding="utf-8")
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
    assert "Sync retention" in html
    assert "Reports" in html
    assert "Sync audit" in html
    assert "Cleanup result" in html
    assert 'class="hero hero-issues"' in html
    assert "Report freshness needs action" in html
    assert "freshness_policy unknown&gt;=1 stale&gt;=1 future&gt;=1 aging&gt;=1" in html
    assert "Report freshness" in html
    assert "Aging reports" in html
    assert "Future reports" in html
    assert "Cleanup freshness" in html
    assert "Cleanup aging reports" in html
    assert "Cleanup future reports" in html
    assert "Stale cleanup reports" in html
    assert "aging 1" in html
    assert "/ 2 total" in html
    assert "fresh 0" in html
    assert "stale 1" in html
    assert "status-prunable" in html
    assert "status-issues" in html
    assert "status-cleaned" in html
    assert "issues_with_findings" in html
    assert "duplicate_entry_key=1" in html
    assert "cleanup_report_mismatches:</strong> 1" in html
    assert "duplicate_entry_key (1): run `republic sync repair --dry-run` to canonicalize duplicate manifest entries" in html
    assert "Cleanup preview: cleanup report issue_filter=3 does not match audit issue_filter=1" in html
    assert 'href="#report-cleanup-result"' in html
    assert 'href="#report-sync-audit"' in html
    assert "comment-proposal" in html
    assert 'data-default-refresh-seconds="30"' in html
    assert 'id="run-search"' in html
    assert payload["counts"]["available_reports"] == 2
    assert payload["counts"]["aging_reports"] == 1
    assert payload["counts"]["future_reports"] == 0
    assert payload["counts"]["stale_reports"] == 1
    assert payload["counts"]["cleanup_reports"] == 1
    assert payload["counts"]["cleanup_aging_reports"] == 0
    assert payload["counts"]["cleanup_future_reports"] == 0
    assert payload["counts"]["cleanup_unknown_reports"] == 0
    assert payload["counts"]["stale_cleanup_reports"] == 1
    assert payload["hero"]["severity"] == "issues"
    assert payload["hero"]["title"] == "Report freshness needs action"
    assert payload["policy"]["summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert payload["reports"]["aging_total"] == 1
    assert payload["reports"]["future_total"] == 0
    assert payload["reports"]["stale_total"] == 1
    assert payload["reports"]["freshness"]["aging"] == 1
    assert payload["reports"]["freshness"]["future"] == 0
    assert payload["reports"]["freshness"]["stale"] == 1
    assert payload["reports"]["freshness_severity"] == "issues"
    assert payload["reports"]["freshness_severity_reason"] == "stale reports need regeneration or operator review"
    assert sum(payload["reports"]["freshness"].values()) == 2
    assert payload["reports"]["cleanup_total"] == 1
    assert payload["reports"]["cleanup_aging_total"] == 0
    assert payload["reports"]["cleanup_future_total"] == 0
    assert payload["reports"]["cleanup_unknown_total"] == 0
    assert payload["reports"]["cleanup_stale_total"] == 1
    assert payload["reports"]["cleanup_freshness"]["stale"] == 1
    assert payload["reports"]["cleanup_freshness_severity"] == "issues"
    assert (
        payload["reports"]["cleanup_freshness_severity_reason"]
        == "stale reports need regeneration or operator review"
    )
    assert payload["reports"]["entries"][0]["label"] == "Sync audit"
    assert payload["reports"]["entries"][0]["metrics"]["cleanup_report_mismatches"] == 1
    assert payload["reports"]["entries"][0]["details"]["action_hints"][0].startswith("duplicate_entry_key (1):")
    assert payload["reports"]["entries"][0]["details"]["cleanup_report_mismatches"] == 1
    assert payload["reports"]["entries"][0]["details"]["cleanup_mismatch_warnings"] == [
        "Cleanup preview: cleanup report issue_filter=3 does not match audit issue_filter=1"
    ]
    assert (
        payload["reports"]["entries"][0]["related_report_detail_summary"]
        == "related report details\n"
        "mismatches\n"
        "- Cleanup preview: cleanup report issue_filter=3 does not match audit issue_filter=1"
    )
    assert payload["reports"]["entries"][0]["details"]["issues_with_findings"] == 2
    assert payload["reports"]["entries"][0]["details"]["finding_counts"]["duplicate_entry_key"] == 1
    assert payload["reports"]["entries"][0]["policy_summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert payload["reports"]["entries"][0]["policy"]["unknown_issues_threshold"] == 1
    assert payload["reports"]["entries"][0]["related_cards"][0]["key"] == "cleanup-result"
    assert payload["reports"]["entries"][1]["label"] == "Cleanup result"
    assert payload["reports"]["entries"][1]["freshness_status"] == "stale"
    assert payload["reports"]["entries"][1]["age_seconds"] is not None
    assert "related report details" in html
    assert "mismatches" in html
    assert payload["reports"]["entries"][1]["policy"]["stale_issues_threshold"] == 1
    assert payload["reports"]["entries"][1]["referenced_by"][0]["key"] == "sync-audit"
    assert "freshness stale" in html
    assert "Policy context" in html
    assert "unknown&gt;=1 stale&gt;=1 future&gt;=1 aging&gt;=1" in html
    assert "## Policy" in markdown
    assert "- report_freshness_policy: unknown>=1 stale>=1 future>=1 aging>=1" in markdown
    assert "## Hero" in markdown
    assert "- severity: issues" in markdown
    assert "## Reports" in markdown
    assert "- report_freshness_severity: issues" in markdown
    assert "- aging_reports: 1" in markdown
    assert "- future_reports: 0" in markdown
    assert "- stale_reports: 1" in markdown
    assert "- reports_by_freshness: aging=1, fresh=0, future=0, stale=1, unknown=0" in markdown
    assert "stale=1" in markdown
    assert "- cleanup_reports: 1" in markdown
    assert "- cleanup_freshness_severity: issues" in markdown
    assert "- cleanup_aging_reports: 0" in markdown
    assert "- cleanup_future_reports: 0" in markdown
    assert "- cleanup_unknown_reports: 0" in markdown
    assert "- stale_cleanup_reports: 1" in markdown
    assert "- cleanup_reports_by_freshness: aging=0, fresh=0, future=0, stale=1, unknown=0" in markdown
    assert "### Cleanup result" in markdown
    assert "- policy: unknown>=1 stale>=1 future>=1 aging>=1" in markdown
    assert "- policy_thresholds: aging_attention_threshold=1, future_attention_threshold=1, stale_issues_threshold=1, unknown_issues_threshold=1" in markdown
    assert "- freshness: stale" in markdown
    assert "cleanup_mismatch_warnings=Cleanup preview: cleanup report issue_filter=3 does not match audit issue_filter=1" in markdown
    assert "- related_report_details:" in markdown
    assert "  - mismatches:" in markdown
    assert "    - Cleanup preview: cleanup report issue_filter=3 does not match audit issue_filter=1" in markdown
    assert "cleanup_report_mismatches=1" in markdown
    assert "action_hints=duplicate_entry_key (1): run `republic sync repair --dry-run` to canonicalize duplicate manifest entries" in markdown
    assert "missing_manifest (1): run `republic sync repair --dry-run` to rebuild manifest state from archived files" in markdown
    assert "sample_issue_ids=4,9" in markdown
    assert "- related_cards: Cleanup result" in markdown
    assert "- referenced_by: Sync audit" in markdown


def test_cli_dashboard_surfaces_unknown_report_freshness_warning(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    reports_dir = demo_repo / ".ai-republic" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "cleanup-preview.json").write_text(
        json.dumps(
            {
                "summary": {
                    "overall_status": "preview",
                    "action_count": 1,
                    "affected_issue_count": 1,
                    "sync_applied_action_count": 1,
                    "replacement_entry_count": 0,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "cleanup-preview.md").write_text("# Cleanup preview\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["dashboard", "--format", "all"],
        catch_exceptions=False,
    )
    dashboard_path = demo_repo / ".ai-republic" / "dashboard" / "index.html"
    dashboard_json = demo_repo / ".ai-republic" / "dashboard" / "index.json"
    dashboard_markdown = demo_repo / ".ai-republic" / "dashboard" / "index.md"
    html = dashboard_path.read_text(encoding="utf-8")
    payload = json.loads(dashboard_json.read_text(encoding="utf-8"))
    markdown = dashboard_markdown.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Unknown freshness reports" in html
    assert "Cleanup unknown freshness reports" in html
    assert 'class="hero hero-issues"' in html
    assert "Report freshness needs action" in html
    assert "unknown 1" in html
    assert payload["counts"]["unknown_reports"] == 1
    assert payload["counts"]["cleanup_unknown_reports"] == 1
    assert payload["reports"]["unknown_total"] == 1
    assert payload["reports"]["cleanup_unknown_total"] == 1
    assert payload["hero"]["severity"] == "issues"
    assert payload["reports"]["freshness"]["unknown"] == 1
    assert payload["reports"]["cleanup_freshness"]["unknown"] == 1
    assert payload["reports"]["freshness_severity"] == "issues"
    assert payload["reports"]["cleanup_freshness_severity"] == "issues"
    assert payload["reports"]["entries"][0]["freshness_status"] == "unknown"
    assert "- severity: issues" in markdown
    assert "- unknown_reports: 1" in markdown
    assert "- report_freshness_severity: issues" in markdown
    assert "- cleanup_freshness_severity: issues" in markdown
    assert "- cleanup_unknown_reports: 1" in markdown
    assert "- reports_by_freshness: aging=0, fresh=0, future=0, stale=0, unknown=1" in markdown
    assert "- cleanup_reports_by_freshness: aging=0, fresh=0, future=0, stale=0, unknown=1" in markdown


def test_cli_dashboard_surfaces_embedded_policy_drift(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(
        "reporepublic.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    unknown_issues_threshold: 2",
                "    stale_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_dashboard_reports(demo_repo)
    report_json = demo_repo / ".ai-republic" / "reports" / "sync-audit.json"
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    payload["policy"] = {
        "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
        "report_freshness_policy": {
            "unknown_issues_threshold": 1,
            "stale_issues_threshold": 1,
            "future_attention_threshold": 1,
            "aging_attention_threshold": 1,
        },
    }
    report_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    result = runner.invoke(
        app,
        ["dashboard", "--format", "all"],
        catch_exceptions=False,
    )

    dashboard_path = demo_repo / ".ai-republic" / "dashboard" / "index.html"
    dashboard_json = demo_repo / ".ai-republic" / "dashboard" / "index.json"
    dashboard_markdown = demo_repo / ".ai-republic" / "dashboard" / "index.md"
    html = dashboard_path.read_text(encoding="utf-8")
    snapshot = json.loads(dashboard_json.read_text(encoding="utf-8"))
    markdown = dashboard_markdown.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Policy drift reports" in html
    assert "re-run `republic sync audit --format all` and `republic clean --report --report-format all`" in html
    assert "embedded policy drift" in html
    assert "embedded policy differs from current config" in html
    assert snapshot["counts"]["policy_drift_reports"] == 1
    assert snapshot["reports"]["policy_drift_total"] == 1
    assert (
        snapshot["reports"]["policy_drift_guidance"]
        == "refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert snapshot["reports"]["entries"][0]["policy_alignment_status"] == "drift"
    assert (
        snapshot["reports"]["entries"][0]["policy_alignment_note"]
        == "embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)"
    )
    assert (
        snapshot["reports"]["entries"][0]["policy_alignment_remediation"]
        == "refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert "- policy_drift_reports: 1" in markdown
    assert "- policy_drift_guidance: refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`" in markdown
    assert "- policy_alignment: drift" in markdown
    assert "- policy_alignment_remediation: refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`" in markdown


def test_cli_dashboard_escalates_hero_when_only_policy_drift_exists(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(
        "reporepublic.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
    reports_dir = demo_repo / ".ai-republic" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "sync-audit.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-08T05:30:00+00:00"},
                "summary": {
                    "overall_status": "clean",
                    "pending_artifacts": 0,
                    "integrity_issue_count": 0,
                    "prunable_groups": 0,
                    "repair_needed_issues": 0,
                },
                "policy": {
                    "summary": "unknown>=9 stale>=9 future>=9 aging>=9",
                    "report_freshness_policy": {
                        "unknown_issues_threshold": 9,
                        "stale_issues_threshold": 9,
                        "future_attention_threshold": 9,
                        "aging_attention_threshold": 9,
                    },
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "sync-audit.md").write_text("# Sync audit\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["dashboard", "--format", "all"],
        catch_exceptions=False,
    )

    dashboard_path = demo_repo / ".ai-republic" / "dashboard" / "index.html"
    dashboard_json = demo_repo / ".ai-republic" / "dashboard" / "index.json"
    dashboard_markdown = demo_repo / ".ai-republic" / "dashboard" / "index.md"
    html = dashboard_path.read_text(encoding="utf-8")
    snapshot = json.loads(dashboard_json.read_text(encoding="utf-8"))
    markdown = dashboard_markdown.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert 'class="hero hero-attention"' in html
    assert "Report policy drift needs follow-up" in html
    assert snapshot["reports"]["freshness_severity"] == "clean"
    assert snapshot["reports"]["policy_drift_severity"] == "attention"
    assert snapshot["reports"]["report_summary_severity"] == "attention"
    assert (
        snapshot["reports"]["report_summary_severity_reason"]
        == "embedded policy drift was detected in raw report exports; refresh raw report exports to align embedded policy metadata"
    )
    assert snapshot["hero"]["severity"] == "attention"
    assert snapshot["hero"]["title"] == "Report policy drift needs follow-up"
    assert snapshot["hero"]["reporting_chips"][1] == {
        "label": "Policy drift",
        "severity": "attention",
        "value": "1 report",
    }
    assert "- report_summary_severity: attention" in markdown
    assert "- policy_drift_severity: attention" in markdown


def test_cli_dashboard_surfaces_related_report_policy_drift_notes(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(
        "reporepublic.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    unknown_issues_threshold: 2",
                "    stale_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_dashboard_reports(demo_repo)
    reports_dir = demo_repo / ".ai-republic" / "reports"
    warning = "embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)"
    alignment = {
        "status": "drift",
        "warning": warning,
        "current_summary": "unknown>=2 stale>=2 future>=2 aging>=2",
        "current_report_freshness_policy": {
            "unknown_issues_threshold": 2,
            "stale_issues_threshold": 2,
            "future_attention_threshold": 2,
            "aging_attention_threshold": 2,
        },
        "embedded_summary": "unknown>=1 stale>=1 future>=1 aging>=1",
        "embedded_report_freshness_policy": {
            "unknown_issues_threshold": 1,
            "stale_issues_threshold": 1,
            "future_attention_threshold": 1,
            "aging_attention_threshold": 1,
        },
    }
    sync_payload = json.loads((reports_dir / "sync-audit.json").read_text(encoding="utf-8"))
    sync_payload["related_reports"]["entries"][0]["policy_alignment"] = alignment
    sync_payload["related_reports"]["policy_drift_reports"] = 1
    sync_payload["related_reports"]["policy_drifts"] = [
        {
            "key": "cleanup-result",
            "label": "Cleanup result",
            "warning": warning,
            "embedded_summary": "unknown>=1 stale>=1 future>=1 aging>=1",
            "current_summary": "unknown>=2 stale>=2 future>=2 aging>=2",
        }
    ]
    sync_payload["summary"]["related_cleanup_policy_drifts"] = 1
    (reports_dir / "sync-audit.json").write_text(
        json.dumps(sync_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    cleanup_payload = json.loads((reports_dir / "cleanup-result.json").read_text(encoding="utf-8"))
    cleanup_payload["related_reports"] = {
        "total_reports": 1,
        "entries": [
            {
                "key": "sync-audit",
                "label": "Sync audit",
                "status": "issues",
                "summary": "pending=1 integrity_issues=2 prunable_groups=1",
                "issue_filter": None,
                "json_path": str(reports_dir / "sync-audit.json"),
                "markdown_path": str(reports_dir / "sync-audit.md"),
                "policy_alignment": alignment,
            }
        ],
        "mismatch_reports": 0,
        "mismatches": [],
        "policy_drift_reports": 1,
        "policy_drifts": [
            {
                "key": "sync-audit",
                "label": "Sync audit",
                "warning": warning,
                "embedded_summary": "unknown>=1 stale>=1 future>=1 aging>=1",
                "current_summary": "unknown>=2 stale>=2 future>=2 aging>=2",
            }
        ],
    }
    cleanup_payload["summary"]["related_sync_audit_reports"] = 1
    cleanup_payload["summary"]["sync_audit_policy_drifts"] = 1
    cleanup_payload["summary"]["sync_audit_issue_filter_mismatches"] = 0
    (reports_dir / "cleanup-result.json").write_text(
        json.dumps(cleanup_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["dashboard", "--format", "all"],
        catch_exceptions=False,
    )
    dashboard_path = demo_repo / ".ai-republic" / "dashboard" / "index.html"
    dashboard_json = demo_repo / ".ai-republic" / "dashboard" / "index.json"
    dashboard_markdown = demo_repo / ".ai-republic" / "dashboard" / "index.md"
    html = dashboard_path.read_text(encoding="utf-8")
    payload = json.loads(dashboard_json.read_text(encoding="utf-8"))
    markdown = dashboard_markdown.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Cleanup result: embedded policy differs from current config" in html
    assert "Sync audit: embedded policy differs from current config" in html
    assert "related report details" in html
    assert "policy drifts" in html
    assert "refresh raw report exports to align embedded policy metadata" in html
    assert payload["reports"]["entries"][0]["related_cards"][0]["policy_alignment_status"] == "drift"
    assert payload["reports"]["entries"][1]["related_cards"][0]["policy_alignment_status"] == "drift"
    assert payload["reports"]["entries"][1]["details"]["related_report_policy_drifts"] == 1
    assert (
        payload["reports"]["entries"][1]["details"]["related_report_policy_drift_warnings"][0]
        == f"Sync audit: {warning}"
    )
    assert (
        payload["reports"]["entries"][1]["related_report_detail_summary"]
        == "related report details\n"
        "policy drifts\n"
        f"- Sync audit: {warning}\n"
        "remediation: refresh raw report exports to align embedded policy metadata; "
        "re-run `republic sync audit --format all` and `republic clean --report "
        "--report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert "related_report_policy_drift_warnings=Sync audit: embedded policy differs from current config" in markdown
    assert "- related_report_details:" in markdown
    assert "  - policy_drifts:" in markdown
    assert f"    - Sync audit: {warning}" in markdown
    assert (
        "  - remediation: refresh raw report exports to align embedded policy metadata; "
        "re-run `republic sync audit --format all` and `republic clean --report "
        "--report-format all` after updating `dashboard.report_freshness_policy`"
    ) in markdown


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


def test_cli_sync_check_reports_manifest_issues(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    applied_root = demo_repo / ".ai-republic" / "sync-applied" / "local-file" / "issue-1"
    applied_root.mkdir(parents=True, exist_ok=True)
    orphan_path = applied_root / "20260308T010105000001Z-comment.md"
    orphan_path.write_text("---\nissue_id: 1\n---\n\nOrphan handoff.\n", encoding="utf-8")

    result = runner.invoke(app, ["sync", "check", "--issue", "1"], catch_exceptions=False)

    assert result.exit_code == 1
    assert "Applied sync manifest check:" in result.stdout
    assert "status=issues" in result.stdout
    assert "missing_manifest" in result.stdout
    assert "orphan_archive_file" in result.stdout


def test_cli_sync_repair_adopts_orphan_archives_and_clears_findings(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    applied_root = demo_repo / ".ai-republic" / "sync-applied" / "local-markdown" / "issue-1"
    applied_root.mkdir(parents=True, exist_ok=True)
    branch_path = applied_root / "20260308T010201000001Z-branch.json"
    branch_path.write_text(
        json.dumps(
            {
                "action": "branch",
                "issue_id": 1,
                "branch_name": "reporepublic/issue-1-fix-empty-input",
                "base_branch": "main",
                "staged_at": "20260308T010201000001Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    preview = runner.invoke(app, ["sync", "repair", "--issue", "1", "--dry-run"], catch_exceptions=False)
    apply_result = runner.invoke(app, ["sync", "repair", "--issue", "1"], catch_exceptions=False)
    manifest_payload = json.loads((applied_root / "manifest.json").read_text(encoding="utf-8"))
    check_result = runner.invoke(app, ["sync", "check", "--issue", "1"], catch_exceptions=False)

    assert preview.exit_code == 0
    assert "Applied sync manifest repair preview:" in preview.stdout
    assert "adopted_archives=1" in preview.stdout
    assert apply_result.exit_code == 0
    assert "Applied sync manifest repair:" in apply_result.stdout
    assert manifest_payload[0]["action"] == "branch"
    assert manifest_payload[0]["handoff"]["group_size"] == 1
    assert check_result.exit_code == 0
    assert "status=ok" in check_result.stdout


def test_cli_sync_audit_writes_default_reports(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    _configure_sync_retention(demo_repo, keep_groups=1)
    _write_cleanup_reports_for_sync_audit(demo_repo)
    pending_dir = demo_repo / ".ai-republic" / "sync" / "local-file" / "issue-1"
    pending_dir.mkdir(parents=True, exist_ok=True)
    (pending_dir / "20260308T020101000001Z-comment.md").write_text(
        "---\nissue_id: 1\nstaged_at: 20260308T020101000001Z\n---\n\nPending maintainer note.\n",
        encoding="utf-8",
    )
    applied_root = demo_repo / ".ai-republic" / "sync-applied" / "local-file" / "issue-1"
    applied_root.mkdir(parents=True, exist_ok=True)
    stale_branch = applied_root / "20260308T010001000001Z-branch.json"
    recent_comment = applied_root / "20260308T010101000001Z-comment.md"
    stale_branch.write_text('{"action":"branch","issue_id":1}\n', encoding="utf-8")
    recent_comment.write_text("---\nissue_id: 1\n---\n\nRecent comment handoff.\n", encoding="utf-8")
    (applied_root / "manifest.json").write_text(
        json.dumps(
            [
                _manifest_entry(
                    tracker="local-file",
                    issue_id=1,
                    action="branch",
                    applied_at="2026-03-08T01:00:01+00:00",
                    staged_at="20260308T010001000001Z",
                    archived_path=stale_branch,
                    group_key="issue:1|head:reporepublic/issue-1-older",
                    artifact_role="branch-proposal",
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

    result = runner.invoke(app, ["sync", "audit"], catch_exceptions=False)
    report_json = demo_repo / ".ai-republic" / "reports" / "sync-audit.json"
    report_markdown = demo_repo / ".ai-republic" / "reports" / "sync-audit.md"
    payload = json.loads(report_json.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert "Sync audit exports:" in result.stdout
    assert "- json:" in result.stdout
    assert "- markdown:" in result.stdout
    assert "Overall status: attention" in result.stdout
    assert "Linked cleanup reports: 2" in result.stdout
    assert report_json.exists()
    assert report_markdown.exists()
    assert payload["policy"]["summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert payload["summary"]["pending_artifacts"] == 1
    assert payload["summary"]["prunable_groups"] == 1
    assert payload["summary"]["related_cleanup_reports"] == 2
    assert payload["summary"]["related_cleanup_policy_drifts"] == 0
    assert payload["related_reports"]["entries"][0]["label"] == "Cleanup preview"
    assert payload["related_reports"]["entries"][0]["policy_alignment"]["status"] == "missing"
    assert payload["retention"]["entries"][0]["status"] == "prunable"


def test_cli_sync_audit_reports_cleanup_policy_drift(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    unknown_issues_threshold: 2",
                "    stale_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_cleanup_reports_for_sync_audit(demo_repo)
    preview_path = demo_repo / ".ai-republic" / "reports" / "cleanup-preview.json"
    payload = json.loads(preview_path.read_text(encoding="utf-8"))
    payload["policy"] = {
        "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
        "report_freshness_policy": {
            "unknown_issues_threshold": 1,
            "stale_issues_threshold": 1,
            "future_attention_threshold": 1,
            "aging_attention_threshold": 1,
        },
    }
    preview_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    result = runner.invoke(app, ["sync", "audit", "--show-remediation"], catch_exceptions=False)
    report_json = demo_repo / ".ai-republic" / "reports" / "sync-audit.json"
    snapshot = json.loads(report_json.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert "Linked cleanup reports: 2" in result.stdout
    assert "Cleanup report policy drifts: 1" in result.stdout
    assert "Related cleanup report details:" in result.stdout
    assert "  policy_drifts:" in result.stdout
    assert (
        "    - Cleanup preview: embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)"
    ) in result.stdout
    assert (
        "  remediation: refresh raw report exports to align embedded policy metadata; "
        "re-run `republic sync audit --format all` and `republic clean --report "
        "--report-format all` after updating `dashboard.report_freshness_policy`"
    ) in result.stdout
    assert snapshot["summary"]["related_cleanup_policy_drifts"] == 1
    assert snapshot["related_reports"]["policy_drift_reports"] == 1


def test_cli_sync_audit_exits_non_zero_on_integrity_issues(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    applied_root = demo_repo / ".ai-republic" / "sync-applied" / "local-markdown" / "issue-7"
    applied_root.mkdir(parents=True, exist_ok=True)
    (applied_root / "20260308T030101000001Z-comment.md").write_text(
        "---\nissue_id: 7\n---\n\nOrphan archive.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["sync", "audit", "--issue", "7", "--tracker", "local-markdown"], catch_exceptions=False)
    report_json = demo_repo / ".ai-republic" / "reports" / "sync-audit.json"
    payload = json.loads(report_json.read_text(encoding="utf-8"))

    assert result.exit_code == 1
    assert "Overall status: issues" in result.stdout
    assert payload["policy"]["report_freshness_policy"]["unknown_issues_threshold"] == 1
    assert payload["summary"]["integrity_issue_count"] == 1
    assert payload["integrity"]["finding_counts"]["missing_manifest"] == 1


def test_cli_sync_audit_reports_cleanup_issue_filter_mismatch(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    _write_cleanup_reports_for_sync_audit(
        demo_repo,
        preview_issue_filter=3,
        result_issue_filter=7,
    )

    result = runner.invoke(app, ["sync", "audit", "--issue", "7"], catch_exceptions=False)
    report_json = demo_repo / ".ai-republic" / "reports" / "sync-audit.json"
    report_markdown = demo_repo / ".ai-republic" / "reports" / "sync-audit.md"
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    markdown = report_markdown.read_text(encoding="utf-8")

    assert result.exit_code == 0
    assert "Linked cleanup reports: 1" in result.stdout
    assert "Cleanup report mismatches: 1" in result.stdout
    assert payload["policy"]["summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert payload["summary"]["cleanup_report_mismatches"] == 1
    assert payload["related_reports"]["entries"][0]["label"] == "Cleanup result"
    assert payload["related_reports"]["mismatches"][0]["label"] == "Cleanup preview"
    assert "### Cleanup report mismatches" in markdown
    assert "issue_filter=3 does not match audit issue_filter=7" in markdown


def test_cli_sync_health_writes_default_reports_and_summarizes_pipeline(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    loaded = load_config(demo_repo)
    pending_dir = loaded.sync_dir / "local-file" / "issue-1"
    pending_dir.mkdir(parents=True, exist_ok=True)
    (pending_dir / "20260308T020101000001Z-comment.md").write_text(
        "---\nissue_id: 1\nstaged_at: 20260308T020101000001Z\n---\n\nPending maintainer note.\n",
        encoding="utf-8",
    )
    applied_root = loaded.sync_applied_dir / "local-file" / "issue-1"
    applied_root.mkdir(parents=True, exist_ok=True)
    (applied_root / "20260308T030101000001Z-comment.md").write_text(
        "---\nissue_id: 1\n---\n\nOrphan archive.\n",
        encoding="utf-8",
    )
    store = RunStateStore(demo_repo / ".ai-republic" / "state" / "runs.json")
    workspace_path = loaded.workspace_root / "issue-1" / "run-stale" / "repo"
    workspace_path.mkdir(parents=True, exist_ok=True)
    artifact_dir = loaded.artifacts_dir / "issue-1" / "run-stale"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    store.upsert(
        RunRecord(
            run_id="run-stale",
            issue_id=1,
            issue_title="Fix empty input crash",
            fingerprint="fp-stale",
            status=RunLifecycle.COMPLETED,
            workspace_path=str(workspace_path),
            summary="completed",
        )
    )

    result = runner.invoke(app, ["sync", "health", "--issue", "1", "--format", "all"], catch_exceptions=False)
    report_json = demo_repo / ".ai-republic" / "reports" / "sync-health.json"
    report_markdown = demo_repo / ".ai-republic" / "reports" / "sync-health.md"
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    markdown = report_markdown.read_text(encoding="utf-8")

    assert result.exit_code == 1
    assert "Sync health exports:" in result.stdout
    assert "Sync health summary: status=issues pending=1 integrity_issues=1" in result.stdout
    assert "Next actions:" in result.stdout
    assert report_json.exists()
    assert report_markdown.exists()
    assert payload["summary"]["overall_status"] == "issues"
    assert payload["summary"]["pending_artifacts"] == 1
    assert payload["summary"]["integrity_issue_count"] == 1
    assert payload["summary"]["cleanup_action_count"] == 2
    assert payload["repair_preview"]["summary"]["changed_reports"] == 1
    assert payload["cleanup_preview"]["summary"]["action_count"] == 2
    assert any(
        "republic clean --sync-applied --dry-run --report" in item
        for item in payload["summary"]["next_actions"]
    )
    assert "# RepoRepublic Sync Health" in markdown
    assert "## Next actions" in markdown
    assert "## Sync repair preview" in markdown


def test_cli_sync_health_can_print_related_report_details(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    unknown_issues_threshold: 2",
                "    stale_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    reports_dir = demo_repo / ".ai-republic" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "cleanup-preview.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-08T05:00:00+00:00"},
                "policy": {
                    "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
                    "report_freshness_policy": {
                        "unknown_issues_threshold": 1,
                        "stale_issues_threshold": 1,
                        "future_attention_threshold": 1,
                        "aging_attention_threshold": 1,
                    },
                },
                "summary": {
                    "overall_status": "preview",
                    "action_count": 1,
                    "affected_issue_count": 1,
                    "sync_applied_action_count": 1,
                    "related_sync_audit_reports": 0,
                    "sync_audit_issue_filter_mismatches": 0,
                    "sync_audit_policy_drifts": 0,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "cleanup-preview.md").write_text("# Cleanup preview\n", encoding="utf-8")
    (reports_dir / "cleanup-result.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-08T05:10:00+00:00", "issue_filter": 3},
                "policy": {
                    "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
                    "report_freshness_policy": {
                        "unknown_issues_threshold": 1,
                        "stale_issues_threshold": 1,
                        "future_attention_threshold": 1,
                        "aging_attention_threshold": 1,
                    },
                },
                "summary": {
                    "overall_status": "cleaned",
                    "action_count": 1,
                    "affected_issue_count": 1,
                    "sync_applied_action_count": 1,
                    "related_sync_audit_reports": 0,
                    "sync_audit_issue_filter_mismatches": 0,
                    "sync_audit_policy_drifts": 0,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "cleanup-result.md").write_text("# Cleanup result\n", encoding="utf-8")
    (reports_dir / "sync-audit.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-08T05:00:00+00:00"},
                "policy": {
                    "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
                    "report_freshness_policy": {
                        "unknown_issues_threshold": 1,
                        "stale_issues_threshold": 1,
                        "future_attention_threshold": 1,
                        "aging_attention_threshold": 1,
                    },
                },
                "summary": {
                    "overall_status": "attention",
                    "pending_artifacts": 1,
                    "integrity_issue_count": 0,
                    "prunable_groups": 1,
                    "repair_needed_issues": 0,
                    "related_cleanup_reports": 0,
                    "cleanup_report_mismatches": 0,
                    "related_cleanup_policy_drifts": 0,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "sync-audit.md").write_text("# Sync audit\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["sync", "health", "--issue", "1", "--show-mismatches", "--show-remediation"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Sync health:" in result.stdout
    assert "- overall_status: attention" in result.stdout
    assert "Related cleanup details:" in result.stdout
    assert "Related sync audit details:" in result.stdout
    assert "  mismatches:" in result.stdout
    assert "  policy_drifts:" in result.stdout
    assert (
        "    - Cleanup result: cleanup report issue_filter=3 does not match audit issue_filter=1"
        in result.stdout
    )
    assert (
        "    - Cleanup preview: embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)"
        in result.stdout
    )
    assert (
        "    - Sync audit: embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)"
        in result.stdout
    )
    assert "  remediation: refresh raw report exports to align embedded policy metadata;" in result.stdout


def test_cli_sync_audit_can_print_cleanup_mismatch_details(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    _write_cleanup_reports_for_sync_audit(
        demo_repo,
        preview_issue_filter=3,
        result_issue_filter=7,
    )

    result = runner.invoke(
        app,
        ["sync", "audit", "--issue", "7", "--show-mismatches"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Cleanup report mismatches: 1" in result.stdout
    assert "Related cleanup report details:" in result.stdout
    assert "  mismatches:" in result.stdout
    assert (
        "    - Cleanup preview: cleanup report issue_filter=3 does not match audit issue_filter=7"
        in result.stdout
    )


def test_cli_sync_audit_groups_cleanup_mismatch_and_policy_drift_details(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    unknown_issues_threshold: 2",
                "    stale_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_cleanup_reports_for_sync_audit(
        demo_repo,
        preview_issue_filter=3,
        result_issue_filter=7,
    )
    result_path = demo_repo / ".ai-republic" / "reports" / "cleanup-result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["policy"] = {
        "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
        "report_freshness_policy": {
            "unknown_issues_threshold": 1,
            "stale_issues_threshold": 1,
            "future_attention_threshold": 1,
            "aging_attention_threshold": 1,
        },
    }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    result = runner.invoke(
        app,
        ["sync", "audit", "--issue", "7", "--show-mismatches", "--show-remediation"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Cleanup report mismatches: 1" in result.stdout
    assert "Cleanup report policy drifts: 1" in result.stdout
    assert "Related cleanup report details:" in result.stdout
    assert "  mismatches:" in result.stdout
    assert "  policy_drifts:" in result.stdout
    assert (
        "    - Cleanup preview: cleanup report issue_filter=3 does not match audit issue_filter=7"
        in result.stdout
    )
    assert (
        "    - Cleanup result: embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)"
        in result.stdout
    )
    assert (
        "  remediation: refresh raw report exports to align embedded policy metadata; "
        "re-run `republic sync audit --format all` and `republic clean --report "
        "--report-format all` after updating `dashboard.report_freshness_policy`"
    ) in result.stdout


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
        lambda loaded, auth_snapshot=None: app_module.DiagnosticCheck(
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
    monkeypatch.setattr(
        app_module,
        "_probe_github_repo_access",
        lambda loaded, auth_snapshot=None: app_module.DiagnosticCheck(
            name="GitHub repo access",
            status="WARN",
            message="demo/repo metadata probe was skipped in test",
            hint="Set GITHUB_TOKEN for a live repo metadata probe.",
        ),
    )

    result = runner.invoke(app, ["doctor"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Report freshness policy: OK (default thresholds (unknown>=1 stale>=1 future>=1 aging>=1))" in result.stdout
    assert (
        "Report policy health: OK "
        "(thresholds unknown>=1 stale>=1 future>=1 aging>=1)"
    ) in result.stdout
    assert "GitHub auth: WARN (GITHUB_TOKEN is not set)" in result.stdout
    assert "hint: Set GITHUB_TOKEN or run `gh auth login`." in result.stdout
    assert "GitHub network: WARN (could not reach https://api.github.com/rate_limit)" in result.stdout
    assert "Template drift: WARN (" in result.stdout
    assert "triage.md" in result.stdout


def test_cli_doctor_warns_on_relaxed_report_freshness_policy(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    unknown_issues_threshold: 6",
                "    stale_issues_threshold: 7",
                "    future_attention_threshold: 3",
                "    aging_attention_threshold: 4",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")

    result = runner.invoke(app, ["doctor"], catch_exceptions=False)

    assert result.exit_code == 0
    assert (
        "Report freshness policy: WARN (issue escalation is heavily relaxed "
        "(unknown>=6 stale>=7 future>=3 aging>=4))"
    ) in result.stdout
    assert (
        "Report policy health: WARN (issue escalation is heavily relaxed "
        "(unknown>=6 stale>=7 future>=3 aging>=4))"
    ) in result.stdout
    assert (
        "hint: Dashboard report health may stay below `issues` until several stale or "
        "unknown reports accumulate."
    ) in result.stdout


def test_cli_doctor_reports_github_publish_readiness_warning(
    demo_git_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_git_repo)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    config_path = demo_git_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("mode: fixture", "mode: rest")
        .replace("allow_open_pr: false", "allow_open_pr: true"),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(
        app_module.shutil,
        "which",
        lambda command: None if command == "gh" else f"/opt/test/{command}",
    )
    monkeypatch.setattr(
        app_module,
        "_probe_github_network",
        lambda loaded: app_module.DiagnosticCheck(
            name="GitHub network",
            status="OK",
            message="https://api.github.com/rate_limit reachable (status 200)",
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_probe_github_repo_access",
        lambda loaded, auth_snapshot=None: app_module.DiagnosticCheck(
            name="GitHub repo access",
            status="OK",
            message="demo/repo reachable (public; default_branch=main)",
        ),
    )

    result = runner.invoke(app, ["doctor"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "GitHub publish readiness: WARN (" in result.stdout
    assert "git remote origin is not configured" in result.stdout


def test_cli_doctor_warns_on_report_policy_export_mismatch(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    unknown_issues_threshold: 2",
                "    stale_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    reports_dir = demo_repo / ".ai-republic" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "sync-audit.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-08T04:00:00+00:00"},
                "policy": {
                    "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
                    "report_freshness_policy": {
                        "unknown_issues_threshold": 1,
                        "stale_issues_threshold": 1,
                        "future_attention_threshold": 1,
                        "aging_attention_threshold": 1,
                    },
                },
                "summary": {"overall_status": "ok"},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")

    result = runner.invoke(app, ["doctor"], catch_exceptions=False)

    assert result.exit_code == 0
    assert (
        "Report policy export alignment: WARN "
        "(1 raw report exports use a different embedded policy)"
    ) in result.stdout
    assert (
        "Report policy health: WARN "
        "(thresholds unknown>=2 stale>=2 future>=2 aging>=2; "
        "1 raw report export uses a different embedded policy)"
    ) in result.stdout
    assert (
        "  related report details:"
    ) in result.stdout
    assert (
        "    policy_drifts:"
    ) in result.stdout
    assert (
        "      - sync-audit.json embedded=unknown>=1 stale>=1 future>=1 aging>=1 "
        "current=unknown>=2 stale>=2 future>=2 aging>=2"
    ) in result.stdout
    assert (
        "    remediation: refresh raw report exports to align embedded policy metadata; "
        "re-run `republic sync audit --format all` and `republic clean --report "
        "--report-format all` after updating `dashboard.report_freshness_policy`"
    ) in result.stdout


def test_cli_doctor_exports_json_and_markdown(demo_repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(demo_repo)
    monkeypatch.setattr(app_module, "_run_version", lambda command: "codex 0.test")
    monkeypatch.setattr(app_module.shutil, "which", lambda command: f"/opt/test/{command}")

    result = runner.invoke(app, ["doctor", "--format", "all"], catch_exceptions=False)

    report_json = demo_repo / ".ai-republic" / "reports" / "doctor.json"
    report_markdown = demo_repo / ".ai-republic" / "reports" / "doctor.md"
    payload = json.loads(report_json.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert "Doctor exports:" in result.stdout
    assert "Doctor summary: status=clean" in result.stdout
    assert report_json.exists()
    assert report_markdown.exists()
    assert payload["config"]["status"] == "ok"
    assert payload["codex"]["status"] == "ok"
    assert payload["tracker"]["kind"] == "github"
    assert payload["summary"]["diagnostic_count"] >= 1
    assert "# Doctor report" in report_markdown.read_text(encoding="utf-8")


def test_cli_doctor_exports_snapshot_when_config_is_invalid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_module.shutil, "which", lambda command: None)

    result = runner.invoke(app, ["doctor", "--format", "json"], catch_exceptions=False)

    report_json = tmp_path / ".ai-republic" / "reports" / "doctor.json"
    payload = json.loads(report_json.read_text(encoding="utf-8"))

    assert result.exit_code == 1
    assert "Doctor exports:" in result.stdout
    assert payload["config"]["status"] == "error"
    assert payload["summary"]["overall_status"] == "issues"
    assert payload["codex"]["status"] == "missing"


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


def _configure_ops_snapshot_retention(
    repo_root: Path,
    *,
    keep_entries: int,
    prune_managed: bool,
) -> None:
    config_path = repo_root / ".ai-republic" / "reporepublic.yaml"
    payload = load_config(repo_root).data.model_dump(mode="json")
    cleanup = payload.setdefault("cleanup", {})
    cleanup["ops_snapshot_keep_entries"] = keep_entries
    cleanup["ops_snapshot_prune_managed"] = prune_managed
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_ops_snapshot_index(repo_root: Path) -> None:
    ops_root = repo_root / ".ai-republic" / "reports" / "ops"
    ops_root.mkdir(parents=True, exist_ok=True)
    latest_bundle_dir = ops_root / "20260309T101500Z"
    previous_bundle_dir = ops_root / "20260309T100000Z"
    latest_bundle_dir.mkdir(parents=True, exist_ok=True)
    previous_bundle_dir.mkdir(parents=True, exist_ok=True)
    latest_bundle_manifest = {
        "meta": {
            "rendered_at": "2026-03-09T10:15:00+00:00",
            "repo_root": str(repo_root),
            "bundle_dir": str(latest_bundle_dir),
            "issue_filter": 1,
            "tracker_filter": "local-file",
        },
        "summary": {
            "overall_status": "clean",
            "component_statuses": {
                "dashboard": "clean",
                "doctor": "clean",
                "status": "clean",
                "sync_audit": "attention",
            },
        },
        "components": {
            "dashboard": {
                "status": "clean",
                "output_paths": {
                    "html": str(latest_bundle_dir / "dashboard.html"),
                    "json": str(latest_bundle_dir / "dashboard.json"),
                },
                "total_runs": 4,
                "visible_runs": 4,
                "report_health_severity": "attention",
                "available_reports": 3,
            },
            "doctor": {
                "status": "clean",
                "output_paths": {
                    "json": str(latest_bundle_dir / "doctor.json"),
                    "markdown": str(latest_bundle_dir / "doctor.md"),
                },
                "diagnostic_count": 5,
                "exit_code": 0,
            },
            "status": {
                "status": "clean",
                "output_paths": {
                    "json": str(latest_bundle_dir / "status.json"),
                    "markdown": str(latest_bundle_dir / "status.md"),
                },
                "total_runs": 4,
                "selected_runs": 2,
                "report_health_severity": "attention",
            },
            "sync_audit": {
                "status": "attention",
                "output_paths": {
                    "json": str(latest_bundle_dir / "sync-audit.json"),
                    "markdown": str(latest_bundle_dir / "sync-audit.md"),
                },
                "overall_status": "attention",
                "pending_artifacts": 1,
                "integrity_issue_count": 1,
                "prunable_groups": 0,
                "related_cleanup_reports": 1,
            },
        },
        "cross_links": [
            {
                "source": "sync_audit",
                "target": "cleanup_preview",
                "status": "attention",
                "reason": "paired in ops snapshot bundle",
            },
            {
                "source": "cleanup_preview",
                "target": "sync_audit",
                "status": "attention",
                "reason": "paired in ops snapshot bundle",
            },
        ],
    }
    previous_bundle_manifest = {
        "meta": {
            "rendered_at": "2026-03-09T10:00:00+00:00",
            "repo_root": str(repo_root),
            "bundle_dir": str(previous_bundle_dir),
            "issue_filter": None,
            "tracker_filter": None,
        },
        "summary": {
            "overall_status": "issues",
            "component_statuses": {
                "dashboard": "issues",
                "doctor": "clean",
            },
        },
        "components": {
            "dashboard": {
                "status": "issues",
                "output_paths": {
                    "html": str(previous_bundle_dir / "dashboard.html"),
                },
                "total_runs": 2,
                "visible_runs": 2,
                "report_health_severity": "issues",
                "available_reports": 2,
            },
            "doctor": {
                "status": "clean",
                "output_paths": {
                    "json": str(previous_bundle_dir / "doctor.json"),
                },
                "diagnostic_count": 3,
                "exit_code": 0,
            },
        },
        "cross_links": [],
    }
    (latest_bundle_dir / "bundle.json").write_text(
        json.dumps(latest_bundle_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (latest_bundle_dir / "bundle.md").write_text("# Latest bundle\n", encoding="utf-8")
    (previous_bundle_dir / "bundle.json").write_text(
        json.dumps(previous_bundle_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (previous_bundle_dir / "bundle.md").write_text("# Previous bundle\n", encoding="utf-8")
    latest_payload = {
        "meta": {
            "generated_at": "2026-03-09T10:16:00+00:00",
            "ops_root": str(ops_root),
            "entry_count": 2,
            "history_limit": 5,
            "dropped_entry_count": 1,
        },
        "latest": {
            "entry_id": "20260309T101500Z",
            "rendered_at": "2026-03-09T10:15:00+00:00",
            "overall_status": "clean",
            "bundle_dir": str(ops_root / "20260309T101500Z"),
            "bundle_relative_dir": "20260309T101500Z",
            "bundle_json": str(ops_root / "20260309T101500Z" / "bundle.json"),
            "bundle_markdown": str(ops_root / "20260309T101500Z" / "bundle.md"),
            "archive": {
                "path": str(ops_root / "20260309T101500Z.tar.gz"),
                "relative_path": "20260309T101500Z.tar.gz",
                "sha256": "a" * 64,
                "size_bytes": 1234,
                "file_count": 8,
                "member_count": 10,
            },
            "component_statuses": {"doctor": "clean", "dashboard": "clean", "sync_audit": "attention"},
        },
    }
    history_payload = {
        "meta": {
            "generated_at": "2026-03-09T10:16:00+00:00",
            "ops_root": str(ops_root),
            "history_limit": 5,
            "entry_count": 2,
            "dropped_entry_count": 1,
        },
        "latest_entry_id": "20260309T101500Z",
        "entries": [
            latest_payload["latest"],
            {
                "entry_id": "20260309T100000Z",
                "rendered_at": "2026-03-09T10:00:00+00:00",
                "overall_status": "issues",
                "bundle_dir": str(ops_root / "20260309T100000Z"),
                "bundle_relative_dir": "20260309T100000Z",
                "bundle_json": str(ops_root / "20260309T100000Z" / "bundle.json"),
                "bundle_markdown": str(ops_root / "20260309T100000Z" / "bundle.md"),
                "archive": None,
                "component_statuses": {"doctor": "clean", "dashboard": "issues"},
            },
        ],
    }
    (ops_root / "latest.json").write_text(json.dumps(latest_payload, indent=2, sort_keys=True), encoding="utf-8")
    (ops_root / "latest.md").write_text("# Latest ops\n", encoding="utf-8")
    (ops_root / "history.json").write_text(json.dumps(history_payload, indent=2, sort_keys=True), encoding="utf-8")
    (ops_root / "history.md").write_text("# Ops history\n", encoding="utf-8")


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


def _write_dashboard_reports(repo_root: Path) -> None:
    reports_dir = repo_root / ".ai-republic" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "sync-audit.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-08T04:00:00+00:00"},
                "summary": {
                    "overall_status": "issues",
                    "pending_artifacts": 1,
                    "integrity_issue_count": 2,
                    "prunable_groups": 1,
                    "repair_needed_issues": 1,
                },
                "integrity": {
                    "total_reports": 4,
                    "issues_with_findings": 2,
                    "clean_issues": 2,
                    "finding_counts": {
                        "duplicate_entry_key": 1,
                        "missing_manifest": 1,
                    },
                    "reports": [
                        {"issue_id": 4, "status": "issues"},
                        {"issue_id": 6, "status": "ok"},
                        {"issue_id": 9, "status": "issues"},
                    ],
                },
                "related_reports": {
                    "total_reports": 1,
                    "mismatch_reports": 1,
                    "entries": [
                        {
                            "key": "cleanup-result",
                            "label": "Cleanup result",
                            "status": "cleaned",
                            "summary": "actions=2 affected_issues=1",
                            "issue_filter": None,
                            "json_path": str(reports_dir / "cleanup-result.json"),
                            "markdown_path": str(reports_dir / "cleanup-result.md"),
                        }
                    ],
                    "mismatches": [
                        {
                            "label": "Cleanup preview",
                            "warning": "cleanup report issue_filter=3 does not match audit issue_filter=1",
                        }
                    ],
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "sync-audit.md").write_text("# Sync audit\n", encoding="utf-8")
    (reports_dir / "cleanup-result.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-04T04:05:00+00:00", "mode": "applied"},
                "summary": {
                    "overall_status": "cleaned",
                    "action_count": 2,
                    "affected_issue_count": 1,
                    "sync_applied_action_count": 1,
                    "replacement_entry_count": 1,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "cleanup-result.md").write_text("# Cleanup result\n", encoding="utf-8")


def _write_cleanup_reports_for_sync_audit(
    repo_root: Path,
    *,
    preview_issue_filter: int | None = None,
    result_issue_filter: int | None = None,
) -> None:
    reports_dir = repo_root / ".ai-republic" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "cleanup-preview.json").write_text(
        json.dumps(
            {
                "meta": {
                    "rendered_at": "2026-03-08T04:00:00+00:00",
                    "mode": "preview",
                    "issue_filter": preview_issue_filter,
                },
                "summary": {
                    "overall_status": "preview",
                    "action_count": 2,
                    "affected_issue_count": 1,
                    "sync_applied_action_count": 1,
                    "replacement_entry_count": 1,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "cleanup-preview.md").write_text("# Cleanup preview\n", encoding="utf-8")
    (reports_dir / "cleanup-result.json").write_text(
        json.dumps(
            {
                "meta": {
                    "rendered_at": "2026-03-08T04:05:00+00:00",
                    "mode": "applied",
                    "issue_filter": result_issue_filter,
                },
                "summary": {
                    "overall_status": "cleaned",
                    "action_count": 1,
                    "affected_issue_count": 1,
                    "sync_applied_action_count": 1,
                    "replacement_entry_count": 0,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "cleanup-result.md").write_text("# Cleanup result\n", encoding="utf-8")
