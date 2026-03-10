from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import yaml

from repoagents.config import load_config
from repoagents.dashboard import build_dashboard
from repoagents.models import ExternalActionResult, RunLifecycle, RunRecord
from repoagents.ops_status import build_ops_status_exports, build_ops_status_snapshot
from repoagents.orchestrator import RunStateStore


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
                "title": "RepoAgents: Fix empty input crash (#1)",
                "head_branch": "repoagents/issue-1-fix-empty-input",
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
        "head_branch: repoagents/issue-1-fix-empty-input\n"
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
                        "bundle_key": "issue:1|head:repoagents/issue-1-fix-empty-input",
                        "refs": {
                            "head": "repoagents/issue-1-fix-empty-input",
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
                        "group_key": "issue:1|head:repoagents/issue-1-fix-empty-input",
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
                        "bundle_key": "issue:1|head:repoagents/issue-1-fix-empty-input",
                        "refs": {
                            "head": "repoagents/issue-1-fix-empty-input",
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
                        "group_key": "issue:1|head:repoagents/issue-1-fix-empty-input",
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
            backend_mode="codex",
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
        formats=("json", "markdown"),
    )
    dashboard_json = result.exported_paths["json"].read_text(encoding="utf-8")
    dashboard_markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")
    payload = json.loads(dashboard_json)

    assert result.total_runs == 1
    assert result.visible_runs == 1
    assert result.output_path == result.exported_paths["markdown"]
    assert set(result.exported_paths) == {"json", "markdown"}
    assert payload["counts"]["total_runs"] == 1
    assert payload["counts"]["total_sync_handoffs"] == 2
    assert payload["runs"][0]["run_id"] == "run-1"
    assert payload["runs"][0]["external_actions"][0]["action"] == "post_comment"
    assert (
        payload["runs"][0]["external_actions"][0]["payload"]["url"]
        == "https://github.example/demo/repo/issues/1#issuecomment-1"
    )
    assert payload["sync_handoffs"][0]["artifact_role"] == "pr-body-proposal"
    assert payload["sync_handoffs"][0]["normalized_links"][0]["label"] == "metadata_artifact"
    assert payload["sync_handoffs"][0]["manifest_path"] == str(manifest_path)
    assert "# RepoAgents Dashboard Snapshot" in dashboard_markdown
    assert "### Issue #1: Fix empty input crash" in dashboard_markdown
    assert "- status: failed" in dashboard_markdown
    assert "Tests did not cover the empty-string branch." in dashboard_markdown
    assert "## Sync handoffs" in dashboard_markdown
    assert "- bundle_key: issue:1|head:repoagents/issue-1-fix-empty-input" in dashboard_markdown


def test_build_dashboard_includes_sync_retention_snapshot(demo_repo: Path) -> None:
    _configure_sync_retention(demo_repo, keep_groups=1)
    loaded = load_config(demo_repo)
    applied_root = loaded.sync_applied_dir / "local-file" / "issue-1"
    applied_root.mkdir(parents=True, exist_ok=True)
    stale_branch = applied_root / "20260308T010001000001Z-branch.json"
    stale_pr = applied_root / "20260308T010002000001Z-pr.json"
    fresh_comment = applied_root / "20260308T010101000001Z-comment.md"
    stale_branch.write_text('{"action":"branch","issue_id":1}\n', encoding="utf-8")
    stale_pr.write_text('{"action":"pr","issue_id":1}\n', encoding="utf-8")
    fresh_comment.write_text("---\nissue_id: 1\n---\n\nRecent comment handoff.\n", encoding="utf-8")
    manifest_entries = [
        _manifest_entry(
            tracker="local-file",
            issue_id=1,
            action="branch",
            applied_at="2026-03-08T01:00:01+00:00",
            staged_at="20260308T010001000001Z",
            archived_path=stale_branch,
            group_key="issue:1|head:repoagents/old-branch",
            artifact_role="branch-proposal",
        ),
        _manifest_entry(
            tracker="local-file",
            issue_id=1,
            action="pr",
            applied_at="2026-03-08T01:00:02+00:00",
            staged_at="20260308T010002000001Z",
            archived_path=stale_pr,
            group_key="issue:1|head:repoagents/old-branch",
            artifact_role="pr-proposal",
        ),
        _manifest_entry(
            tracker="local-file",
            issue_id=1,
            action="comment",
            applied_at="2026-03-08T01:01:01+00:00",
            staged_at="20260308T010101000001Z",
            archived_path=fresh_comment,
            group_key="issue:1|comment",
            artifact_role="comment-proposal",
        ),
    ]
    old_group_entry_keys = [
        str(manifest_entries[0]["entry_key"]),
        str(manifest_entries[1]["entry_key"]),
    ]
    old_group_paths = [
        str(manifest_entries[0]["source_relative_path"]),
        str(manifest_entries[1]["source_relative_path"]),
    ]
    manifest_entries[0]["handoff"] = {
        "group_key": "issue:1|head:repoagents/old-branch",
        "group_size": 2,
        "group_index": 0,
        "group_actions": ["branch", "pr"],
        "related_entry_keys": old_group_entry_keys,
        "related_source_paths": old_group_paths,
    }
    manifest_entries[1]["handoff"] = {
        "group_key": "issue:1|head:repoagents/old-branch",
        "group_size": 2,
        "group_index": 1,
        "group_actions": ["branch", "pr"],
        "related_entry_keys": old_group_entry_keys,
        "related_source_paths": old_group_paths,
    }
    (applied_root / "manifest.json").write_text(
        json.dumps(manifest_entries, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")

    assert payload["sync_retention"]["keep_groups_per_issue"] == 1
    assert payload["sync_retention"]["prunable_groups"] == 1
    assert payload["sync_retention"]["entries"][0]["status"] == "prunable"
    assert payload["sync_retention"]["entries"][0]["prunable_bytes"] > 0
    assert payload["sync_retention"]["entries"][0]["groups"][0]["status"] == "kept"
    assert payload["sync_retention"]["entries"][0]["groups"][1]["status"] == "prunable"
    assert "## Sync retention" in markdown
    assert "- prunable_groups: 1" in markdown
    assert "### local-file · issue #1" in markdown
    assert "status: prunable" in markdown


def test_build_dashboard_includes_report_exports(demo_repo: Path, monkeypatch) -> None:
    loaded = load_config(demo_repo)
    _write_dashboard_reports(demo_repo)
    monkeypatch.setattr(
        "repoagents.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )

    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")
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
    assert payload["hero"]["reporting_chips"][0]["severity"] == "issues"
    assert payload["hero"]["reporting_chips"][1]["severity"] == "issues"
    assert payload["policy"]["summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert payload["policy"]["report_freshness_policy"]["stale_issues_threshold"] == 1
    assert payload["reports"]["total"] == 2
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
    assert payload["reports"]["entries"][0]["status"] == "attention"
    assert payload["reports"]["entries"][0]["metrics"]["cleanup_report_mismatches"] == 1
    assert any(
        hint.startswith("missing_manifest (1):")
        for hint in payload["reports"]["entries"][0]["details"]["action_hints"]
    )
    assert payload["reports"]["entries"][0]["details"]["cleanup_report_mismatches"] == 1
    assert payload["reports"]["entries"][0]["details"]["cleanup_mismatch_warnings"] == [
        "Cleanup result: cleanup report issue_filter=9 does not match audit issue_filter=7"
    ]
    assert (
        payload["reports"]["entries"][0]["related_report_detail_summary"]
        == "related report details\n"
        "mismatches\n"
        "- Cleanup result: cleanup report issue_filter=9 does not match audit issue_filter=7"
    )
    assert payload["reports"]["entries"][0]["details"]["issues_with_findings"] == 1
    assert payload["reports"]["entries"][0]["details"]["finding_counts"]["missing_manifest"] == 1
    assert payload["reports"]["entries"][0]["details"]["sample_issue_ids"] == [7]
    assert payload["reports"]["entries"][0]["policy_summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert payload["reports"]["entries"][0]["policy"]["unknown_issues_threshold"] == 1
    assert payload["reports"]["entries"][0]["related_cards"][0]["key"] == "cleanup-preview"
    assert payload["reports"]["entries"][1]["label"] == "Cleanup preview"
    assert payload["reports"]["entries"][1]["freshness_status"] == "stale"
    assert payload["reports"]["entries"][1]["age_seconds"] is not None
    assert payload["reports"]["entries"][1]["metrics"]["action_count"] == 3
    assert payload["reports"]["entries"][1]["policy"]["stale_issues_threshold"] == 1
    assert payload["reports"]["entries"][1]["referenced_by"][0]["key"] == "sync-audit"
    assert "## Policy" in markdown
    assert "- report_freshness_policy: unknown>=1 stale>=1 future>=1 aging>=1" in markdown
    assert "- stale_issues_threshold: 1" in markdown
    assert "## Hero" in markdown
    assert "- severity: issues" in markdown
    assert "- title: Report freshness needs action" in markdown
    assert "Report freshness: severity=issues value=fresh 0 · aging 1 · stale 1 / 2 total" in markdown
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
    assert "### Sync audit" in markdown
    assert "### Cleanup preview" in markdown
    assert "- policy: unknown>=1 stale>=1 future>=1 aging>=1" in markdown
    assert "- policy_thresholds: aging_attention_threshold=1, future_attention_threshold=1, stale_issues_threshold=1, unknown_issues_threshold=1" in markdown
    assert "- metrics: cleanup_report_mismatches=1, integrity_issue_count=1, pending_artifacts=2, prunable_groups=1, repair_needed_issues=1" in markdown
    assert "- details:" in markdown
    assert "cleanup_mismatch_warnings=Cleanup result: cleanup report issue_filter=9 does not match audit issue_filter=7" in markdown
    assert "- related_report_details:" in markdown
    assert "  - mismatches:" in markdown
    assert "    - Cleanup result: cleanup report issue_filter=9 does not match audit issue_filter=7" in markdown
    assert "cleanup_report_mismatches=1" in markdown
    assert "missing_manifest (1): run `repoagents sync repair --dry-run` to rebuild manifest state from archived files" in markdown
    assert "orphan_archive (2): review the affected manifest entries and rerun `repoagents sync check` after repair" in markdown
    assert "sample_issue_ids=7" in markdown


def test_build_dashboard_includes_ops_snapshot_index(demo_repo: Path, monkeypatch) -> None:
    loaded = load_config(demo_repo)
    _write_ops_snapshot_index(demo_repo)
    monkeypatch.setattr(
        "repoagents.dashboard.utc_now",
        lambda: datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )

    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")
    assert payload["counts"]["ops_snapshot_entries"] == 2
    assert payload["counts"]["ops_snapshot_archives"] == 1
    assert payload["counts"]["ops_snapshot_dropped_entries"] == 1
    assert payload["ops_snapshots"]["status"] == "available"
    assert payload["ops_snapshots"]["history_limit"] == 5
    assert payload["ops_snapshots"]["dropped_entry_count"] == 1
    assert payload["ops_snapshots"]["latest"]["entry_id"] == "20260309T101500Z"
    assert payload["ops_snapshots"]["latest"]["has_archive"] is True
    assert payload["ops_snapshots"]["latest"]["landing_html"].endswith("index.html")
    assert payload["ops_snapshots"]["latest"]["brief_headline"] == "Sync audit still needs follow-up."
    assert payload["ops_snapshots"]["entries"][0]["entry_id"] == "20260309T101500Z"
    assert "# RepoAgents Dashboard Snapshot" in markdown
    assert "## Ops snapshots" in markdown
    assert "- history_entry_count: 2" in markdown
    assert "- history_limit: 5" in markdown
    assert "- dropped_entry_count: 1" in markdown
    assert "  - entry_id: 20260309T101500Z" in markdown
    assert "  - landing_html: " in markdown
    assert "  - 20260309T101500Z: status=clean" in markdown


def test_build_dashboard_surfaces_ops_status_report_and_cross_links(
    demo_repo: Path,
    monkeypatch,
) -> None:
    loaded = load_config(demo_repo)
    _write_dashboard_reports(demo_repo)
    _write_ops_snapshot_index(demo_repo)
    monkeypatch.setattr(
        "repoagents.ops_status.utc_now",
        lambda: datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )
    build_ops_status_exports(
        snapshot=build_ops_status_snapshot(loaded=loaded, history_preview_limit=2),
        output_path=loaded.reports_dir / "ops-status.json",
        formats=("json", "markdown"),
    )
    monkeypatch.setattr(
        "repoagents.dashboard.utc_now",
        lambda: datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )

    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")

    ops_status_entry = next(
        entry for entry in payload["reports"]["entries"] if entry["key"] == "ops-status"
    )

    assert payload["reports"]["total"] == 3
    assert ops_status_entry["status"] == "clean"
    assert ops_status_entry["metrics"]["related_report_count"] == 2
    assert ops_status_entry["details"]["latest_bundle_component_count"] == 5
    assert ops_status_entry["related_cards"][0]["key"] == "ops-brief"
    assert ops_status_entry["related_cards"][1]["key"] == "sync-audit"
    assert "### Ops status" in markdown
    assert "- related_cards: Ops brief, Sync audit" in markdown


def test_build_dashboard_surfaces_sync_health_report_and_relations(
    demo_repo: Path,
    monkeypatch,
) -> None:
    loaded = load_config(demo_repo)
    _write_dashboard_reports(demo_repo)
    _write_sync_health_report(demo_repo)
    monkeypatch.setattr(
        "repoagents.dashboard.utc_now",
        lambda: datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )

    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")

    sync_health_entry = next(
        entry for entry in payload["reports"]["entries"] if entry["key"] == "sync-health"
    )

    assert sync_health_entry["status"] == "attention"
    assert sync_health_entry["summary"] == "pending=2 integrity_issues=1 cleanup_actions=3"
    assert sync_health_entry["metrics"]["repair_changed_reports"] == 1
    assert sync_health_entry["metrics"]["related_report_mismatches"] == 1
    assert sync_health_entry["details"]["cleanup_related_report_count"] == 2
    assert sync_health_entry["details"]["sync_audit_related_report_count"] == 1
    assert sync_health_entry["related_cards"][0]["key"] == "cleanup-preview"
    assert sync_health_entry["related_cards"][1]["key"] == "cleanup-result"
    assert sync_health_entry["related_cards"][2]["key"] == "sync-audit"
    assert "### Sync health" in markdown
    assert "- related_cards: Cleanup preview, Cleanup result, Sync audit" in markdown
    assert "Cleanup preview: cleanup report issue_filter=9 does not match audit issue_filter=7" in markdown


def test_build_dashboard_surfaces_github_smoke_report(
    demo_repo: Path,
    monkeypatch,
) -> None:
    loaded = load_config(demo_repo)
    _write_dashboard_reports(demo_repo)
    _write_github_smoke_report(demo_repo)
    monkeypatch.setattr(
        "repoagents.dashboard.utc_now",
        lambda: datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )

    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")

    github_smoke_entry = next(
        entry for entry in payload["reports"]["entries"] if entry["key"] == "github-smoke"
    )

    assert github_smoke_entry["status"] == "attention"
    assert github_smoke_entry["metrics"]["branch_policy_status"] == "warn"
    assert github_smoke_entry["details"]["default_branch"] == "main"
    assert github_smoke_entry["details"]["publish_warning_count"] == 2
    assert "### GitHub smoke" in markdown
    assert "branch_policy_status=warn" in markdown


def test_build_dashboard_surfaces_unknown_report_freshness_warning(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    reports_dir = demo_repo / ".ai-repoagents" / "reports"
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

    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")

    assert payload["counts"]["unknown_reports"] == 1
    assert payload["counts"]["cleanup_unknown_reports"] == 1
    assert payload["reports"]["unknown_total"] == 1
    assert payload["reports"]["cleanup_unknown_total"] == 1
    assert payload["reports"]["freshness"]["unknown"] == 1
    assert payload["reports"]["cleanup_freshness"]["unknown"] == 1
    assert payload["hero"]["severity"] == "issues"
    assert payload["reports"]["freshness_severity"] == "issues"
    assert payload["reports"]["cleanup_freshness_severity"] == "issues"
    assert payload["reports"]["entries"][0]["freshness_status"] == "unknown"
    assert "- unknown_reports: 1" in markdown
    assert "- severity: issues" in markdown
    assert "- report_freshness_severity: issues" in markdown
    assert "- cleanup_freshness_severity: issues" in markdown
    assert "- cleanup_unknown_reports: 1" in markdown
    assert "- reports_by_freshness: aging=0, fresh=0, future=0, stale=0, unknown=1" in markdown
    assert "- cleanup_reports_by_freshness: aging=0, fresh=0, future=0, stale=0, unknown=1" in markdown


def test_build_dashboard_applies_report_freshness_policy_thresholds(
    demo_repo: Path,
    monkeypatch,
) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    stale_issues_threshold: 2",
                "    unknown_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "repoagents.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
    loaded = load_config(demo_repo)
    _write_dashboard_reports(demo_repo)

    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")

    assert payload["policy"]["summary"] == "unknown>=2 stale>=2 future>=2 aging>=2"
    assert payload["policy"]["report_freshness_policy"]["unknown_issues_threshold"] == 2
    assert payload["reports"]["freshness_severity"] == "attention"
    assert payload["reports"]["freshness_severity_reason"] == "stale reports are below the issue threshold but should be refreshed"
    assert payload["reports"]["cleanup_freshness_severity"] == "attention"
    assert (
        payload["reports"]["cleanup_freshness_severity_reason"]
        == "stale reports are below the issue threshold but should be refreshed"
    )
    assert payload["hero"]["severity"] == "attention"
    assert payload["hero"]["title"] == "Report freshness needs follow-up"
    assert payload["reports"]["entries"][0]["policy_summary"] == "unknown>=2 stale>=2 future>=2 aging>=2"
    assert payload["reports"]["entries"][0]["policy"]["future_attention_threshold"] == 2
    assert "## Policy" in markdown
    assert "- report_freshness_policy: unknown>=2 stale>=2 future>=2 aging>=2" in markdown
    assert "- policy: unknown>=2 stale>=2 future>=2 aging>=2" in markdown
    assert "- report_freshness_severity: attention" in markdown
    assert "- severity: attention" in markdown
    assert "- cleanup_freshness_severity: attention" in markdown


def test_build_dashboard_detects_embedded_policy_drift(
    demo_repo: Path,
    monkeypatch,
) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    stale_issues_threshold: 2",
                "    unknown_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "repoagents.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
    loaded = load_config(demo_repo)
    _write_dashboard_reports(demo_repo)
    sync_audit_path = demo_repo / ".ai-repoagents" / "reports" / "sync-audit.json"
    payload = json.loads(sync_audit_path.read_text(encoding="utf-8"))
    payload["policy"] = {
        "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
        "report_freshness_policy": {
            "unknown_issues_threshold": 1,
            "stale_issues_threshold": 1,
            "future_attention_threshold": 1,
            "aging_attention_threshold": 1,
        },
    }
    sync_audit_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    snapshot = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")

    assert snapshot["counts"]["policy_drift_reports"] == 1
    assert snapshot["counts"]["policy_embedded_reports"] == 1
    assert snapshot["counts"]["policy_metadata_missing_reports"] == 1
    assert snapshot["reports"]["policy_drift_total"] == 1
    assert snapshot["reports"]["policy_embedded_total"] == 1
    assert snapshot["reports"]["policy_missing_total"] == 1
    assert (
        snapshot["reports"]["policy_drift_guidance"]
        == "refresh raw report exports to align embedded policy metadata; re-run `repoagents sync audit --format all` and `repoagents clean --report --report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert snapshot["reports"]["entries"][0]["policy_alignment_status"] == "drift"
    assert (
        snapshot["reports"]["entries"][0]["embedded_policy_summary"]
        == "unknown>=1 stale>=1 future>=1 aging>=1"
    )
    assert snapshot["reports"]["entries"][0]["embedded_policy"]["stale_issues_threshold"] == 1
    assert (
        snapshot["reports"]["entries"][0]["policy_alignment_note"]
        == "embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)"
    )
    assert (
        snapshot["reports"]["entries"][0]["policy_alignment_remediation"]
        == "refresh raw report exports to align embedded policy metadata; re-run `repoagents sync audit --format all` and `repoagents clean --report --report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert snapshot["reports"]["entries"][1]["policy_alignment_status"] == "missing"
    assert "- policy_drift_reports: 1" in markdown
    assert "- policy_drift_guidance: refresh raw report exports to align embedded policy metadata; re-run `repoagents sync audit --format all` and `repoagents clean --report --report-format all` after updating `dashboard.report_freshness_policy`" in markdown
    assert "- policy_embedded_reports: 1" in markdown
    assert "- reports_without_embedded_policy: 1" in markdown
    assert "- policy_alignment: drift" in markdown
    assert "- embedded_policy: unknown>=1 stale>=1 future>=1 aging>=1" in markdown
    assert "- policy_alignment_remediation: refresh raw report exports to align embedded policy metadata; re-run `repoagents sync audit --format all` and `repoagents clean --report --report-format all` after updating `dashboard.report_freshness_policy`" in markdown


def test_build_dashboard_escalates_hero_when_only_policy_drift_exists(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "repoagents.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
    loaded = load_config(demo_repo)
    reports_dir = demo_repo / ".ai-repoagents" / "reports"
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

    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    snapshot = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")

    assert snapshot["reports"]["freshness_severity"] == "clean"
    assert snapshot["reports"]["policy_drift_severity"] == "attention"
    assert snapshot["reports"]["report_summary_severity"] == "attention"
    assert (
        snapshot["reports"]["report_summary_severity_reason"]
        == "embedded policy drift was detected in raw report exports; refresh raw report exports to align embedded policy metadata"
    )
    assert snapshot["hero"]["severity"] == "attention"
    assert snapshot["hero"]["title"] == "Report policy drift needs follow-up"
    assert snapshot["hero"]["reporting_chips"][0]["label"] == "Report freshness"
    assert snapshot["hero"]["reporting_chips"][0]["severity"] == "attention"
    assert snapshot["hero"]["reporting_chips"][1] == {
        "label": "Policy drift",
        "severity": "attention",
        "value": "1 report",
    }
    assert "- report_freshness_severity: clean" in markdown
    assert "- report_summary_severity: attention" in markdown
    assert "- policy_drift_severity: attention" in markdown
    assert "- title: Report policy drift needs follow-up" in markdown
    assert "- Policy drift: severity=attention value=1 report" in markdown


def test_build_dashboard_surfaces_related_report_policy_drift_notes(
    demo_repo: Path,
    monkeypatch,
) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n"
        + "\n".join(
            [
                "dashboard:",
                "  report_freshness_policy:",
                "    stale_issues_threshold: 2",
                "    unknown_issues_threshold: 2",
                "    future_attention_threshold: 2",
                "    aging_attention_threshold: 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "repoagents.dashboard.utc_now",
        lambda: datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
    _write_dashboard_reports(demo_repo)
    reports_dir = demo_repo / ".ai-repoagents" / "reports"
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
            "key": "cleanup-preview",
            "label": "Cleanup preview",
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
    cleanup_payload = json.loads((reports_dir / "cleanup-preview.json").read_text(encoding="utf-8"))
    cleanup_payload["related_reports"] = {
        "total_reports": 1,
        "entries": [
            {
                "key": "sync-audit",
                "label": "Sync audit",
                "status": "attention",
                "summary": "pending=2 integrity_issues=1 prunable_groups=1",
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
    (reports_dir / "cleanup-preview.json").write_text(
        json.dumps(cleanup_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    result = build_dashboard(
        loaded,
        limit=10,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.exported_paths["json"].read_text(encoding="utf-8"))
    markdown = result.exported_paths["markdown"].read_text(encoding="utf-8")

    assert payload["reports"]["entries"][0]["related_cards"][0]["policy_alignment_status"] == "drift"
    assert payload["reports"]["entries"][1]["related_cards"][0]["policy_alignment_status"] == "drift"
    assert payload["reports"]["entries"][1]["details"]["related_report_policy_drifts"] == 1
    assert payload["reports"]["entries"][1]["details"]["related_report_policy_drift_warnings"] == [
        f"Sync audit: {warning}"
    ]
    assert (
        payload["reports"]["entries"][1]["related_report_detail_summary"]
        == "related report details\n"
        "policy drifts\n"
        f"- Sync audit: {warning}\n"
        "remediation: refresh raw report exports to align embedded policy metadata; "
        "re-run `repoagents sync audit --format all` and `repoagents clean --report "
        "--report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert "related_report_policy_drift_warnings=Sync audit: embedded policy differs from current config" in markdown
    assert "- related_report_details:" in markdown
    assert "  - policy_drifts:" in markdown
    assert f"    - Sync audit: {warning}" in markdown
    assert (
        "  - remediation: refresh raw report exports to align embedded policy metadata; "
        "re-run `repoagents sync audit --format all` and `repoagents clean --report "
        "--report-format all` after updating `dashboard.report_freshness_policy`"
    ) in markdown


def _configure_sync_retention(repo_root: Path, *, keep_groups: int) -> None:
    config_path = repo_root / ".ai-repoagents" / "repoagents.yaml"
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


def _write_dashboard_reports(repo_root: Path) -> None:
    reports_dir = repo_root / ".ai-repoagents" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "sync-audit.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-08T02:00:00+00:00"},
                "summary": {
                    "overall_status": "attention",
                    "pending_artifacts": 2,
                    "integrity_issue_count": 1,
                    "prunable_groups": 1,
                    "repair_needed_issues": 1,
                },
                "integrity": {
                    "total_reports": 3,
                    "issues_with_findings": 1,
                    "clean_issues": 2,
                    "finding_counts": {
                        "missing_manifest": 1,
                        "orphan_archive": 2,
                    },
                    "reports": [
                        {"issue_id": 7, "status": "issues"},
                        {"issue_id": 8, "status": "ok"},
                    ],
                },
                "related_reports": {
                    "total_reports": 1,
                    "mismatch_reports": 1,
                    "entries": [
                        {
                            "key": "cleanup-preview",
                            "label": "Cleanup preview",
                            "status": "preview",
                            "summary": "actions=3 affected_issues=1",
                            "issue_filter": None,
                            "json_path": str(reports_dir / "cleanup-preview.json"),
                            "markdown_path": str(reports_dir / "cleanup-preview.md"),
                        }
                    ],
                    "mismatches": [
                        {
                            "label": "Cleanup result",
                            "warning": "cleanup report issue_filter=9 does not match audit issue_filter=7",
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
    (reports_dir / "cleanup-preview.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-05T02:05:00+00:00", "mode": "preview"},
                "summary": {
                    "overall_status": "preview",
                    "action_count": 3,
                    "affected_issue_count": 1,
                    "sync_applied_action_count": 2,
                    "replacement_entry_count": 1,
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "cleanup-preview.md").write_text("# Cleanup preview\n", encoding="utf-8")


def _write_sync_health_report(repo_root: Path) -> None:
    reports_dir = repo_root / ".ai-repoagents" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "sync-health.json").write_text(
        json.dumps(
            {
                "meta": {"rendered_at": "2026-03-09T02:30:00+00:00"},
                "summary": {
                    "overall_status": "attention",
                    "pending_artifacts": 2,
                    "integrity_issue_count": 1,
                    "repair_changed_reports": 1,
                    "repair_findings_after": 0,
                    "cleanup_action_count": 3,
                    "cleanup_sync_applied_action_count": 2,
                    "prunable_groups": 1,
                    "repair_needed_issues": 1,
                    "related_cleanup_reports": 2,
                    "related_sync_audit_reports": 1,
                    "related_report_mismatches": 1,
                    "related_report_policy_drifts": 1,
                    "next_actions": [
                        "Run repoagents sync repair --dry-run --issue 7",
                        "Review cleanup preview before pruning",
                    ],
                },
                "related_reports": {
                    "cleanup_reports": {
                        "total_reports": 2,
                        "mismatch_reports": 1,
                        "policy_drift_reports": 1,
                        "mismatches": [
                            {
                                "label": "Cleanup preview",
                                "warning": "cleanup report issue_filter=9 does not match audit issue_filter=7",
                            }
                        ],
                        "policy_drifts": [
                            {
                                "label": "Cleanup result",
                                "warning": "embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)",
                            }
                        ],
                        "detail_summary": "Cleanup preview: cleanup report issue_filter=9 does not match audit issue_filter=7\nCleanup result: embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)",
                    },
                    "sync_audit_reports": {
                        "total_reports": 1,
                        "mismatch_reports": 0,
                        "policy_drift_reports": 1,
                        "mismatches": [],
                        "policy_drifts": [
                            {
                                "label": "Sync audit",
                                "warning": "embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)",
                            }
                        ],
                        "detail_summary": "Sync audit: embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)",
                    },
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "sync-health.md").write_text("# Sync health\n", encoding="utf-8")


def _write_github_smoke_report(repo_root: Path) -> None:
    reports_dir = repo_root / ".ai-repoagents" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "github-smoke.json").write_text(
        json.dumps(
            {
                "meta": {
                    "rendered_at": "2026-03-09T02:10:00+00:00",
                    "tracker_repo": "demo/repo",
                    "requested_issue_id": 7,
                },
                "summary": {
                    "status": "attention",
                    "message": "branch policy: default branch main is not protected",
                    "open_issue_count": 2,
                    "sampled_issue_id": 7,
                    "auth_status": "ok",
                    "repo_access_status": "ok",
                    "branch_policy_status": "warn",
                    "publish_status": "warn",
                },
                "repo_access": {
                    "status": "ok",
                    "message": "loaded repo metadata for demo/repo",
                    "full_name": "demo/repo",
                    "default_branch": "main",
                },
                "branch_policy": {
                    "status": "warn",
                    "message": "default branch main is not protected",
                    "warnings": [
                        "default branch main is not protected",
                        "default branch main does not require pull request reviews",
                    ],
                },
                "publish": {
                    "status": "warn",
                    "message": "branch policy: default branch main is not protected",
                    "warnings": [
                        "branch policy: default branch main is not protected",
                        "branch policy: default branch main does not require pull request reviews",
                    ],
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (reports_dir / "github-smoke.md").write_text("# GitHub smoke report\n", encoding="utf-8")


def _write_ops_snapshot_index(repo_root: Path) -> None:
    ops_root = repo_root / ".ai-repoagents" / "reports" / "ops"
    ops_root.mkdir(parents=True, exist_ok=True)
    latest_bundle_dir = ops_root / "20260309T101500Z"
    previous_bundle_dir = ops_root / "20260309T100000Z"
    latest_bundle_dir.mkdir(parents=True, exist_ok=True)
    previous_bundle_dir.mkdir(parents=True, exist_ok=True)
    (latest_bundle_dir / "index.html").write_text("<html>latest</html>\n", encoding="utf-8")
    (latest_bundle_dir / "README.md").write_text("# Latest landing\n", encoding="utf-8")
    (previous_bundle_dir / "index.html").write_text("<html>previous</html>\n", encoding="utf-8")
    (previous_bundle_dir / "README.md").write_text("# Previous landing\n", encoding="utf-8")
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
                "ops_brief": "attention",
                "status": "clean",
                "sync_audit": "attention",
            },
        },
        "landing": {
            "html_path": str(latest_bundle_dir / "index.html"),
            "markdown_path": str(latest_bundle_dir / "README.md"),
            "bundle_json_path": str(latest_bundle_dir / "bundle.json"),
            "bundle_markdown_path": str(latest_bundle_dir / "bundle.md"),
        },
        "components": {
            "dashboard": {
                "status": "clean",
                "output_paths": {
                    "json": str(latest_bundle_dir / "dashboard.json"),
                    "markdown": str(latest_bundle_dir / "dashboard.md"),
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
            "ops_brief": {
                "status": "attention",
                "output_paths": {
                    "json": str(latest_bundle_dir / "ops-brief.json"),
                    "markdown": str(latest_bundle_dir / "ops-brief.md"),
                },
                "headline": "Sync audit still needs follow-up.",
                "top_finding_count": 1,
                "next_action_count": 2,
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
        "landing": {
            "html_path": str(previous_bundle_dir / "index.html"),
            "markdown_path": str(previous_bundle_dir / "README.md"),
            "bundle_json_path": str(previous_bundle_dir / "bundle.json"),
            "bundle_markdown_path": str(previous_bundle_dir / "bundle.md"),
        },
        "components": {
            "dashboard": {
                "status": "issues",
                "output_paths": {
                    "markdown": str(previous_bundle_dir / "dashboard.md"),
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
            "landing_html": str(ops_root / "20260309T101500Z" / "index.html"),
            "landing_markdown": str(ops_root / "20260309T101500Z" / "README.md"),
            "brief_json": str(ops_root / "20260309T101500Z" / "ops-brief.json"),
            "brief_markdown": str(ops_root / "20260309T101500Z" / "ops-brief.md"),
            "brief_severity": "attention",
            "brief_headline": "Sync audit still needs follow-up.",
            "brief_top_finding_count": 1,
            "brief_next_action_count": 2,
            "archive": {
                "path": str(ops_root / "20260309T101500Z.tar.gz"),
                "relative_path": "20260309T101500Z.tar.gz",
                "sha256": "a" * 64,
                "size_bytes": 1234,
                "file_count": 8,
                "member_count": 10,
            },
            "component_statuses": {"doctor": "clean", "dashboard": "clean", "ops_brief": "attention", "sync_audit": "attention"},
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
                "landing_html": str(ops_root / "20260309T100000Z" / "index.html"),
                "landing_markdown": str(ops_root / "20260309T100000Z" / "README.md"),
                "archive": None,
                "component_statuses": {"doctor": "clean", "dashboard": "issues"},
            },
        ],
    }
    (ops_root / "latest.json").write_text(json.dumps(latest_payload, indent=2, sort_keys=True), encoding="utf-8")
    (ops_root / "latest.md").write_text("# Latest ops\n", encoding="utf-8")
    (ops_root / "history.json").write_text(json.dumps(history_payload, indent=2, sort_keys=True), encoding="utf-8")
    (ops_root / "history.md").write_text("# Ops history\n", encoding="utf-8")
