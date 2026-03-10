from __future__ import annotations

import json
from pathlib import Path

import yaml

from repoagents.cli.app import CleanAction
from repoagents.config import load_config
from repoagents.sync_health import build_sync_health_report, build_sync_health_snapshot


def test_build_sync_health_report_writes_combined_exports(
    demo_repo: Path,
) -> None:
    loaded = load_config(demo_repo)
    pending_dir = loaded.sync_dir / "local-file" / "issue-1"
    pending_dir.mkdir(parents=True, exist_ok=True)
    (pending_dir / "20260308T020101000001Z-comment.md").write_text(
        "---\nissue_id: 1\nstaged_at: 20260308T020101000001Z\n---\n\nPending maintainer note.\n",
        encoding="utf-8",
    )

    applied_root = loaded.sync_applied_dir / "local-file" / "issue-1"
    applied_root.mkdir(parents=True, exist_ok=True)
    (applied_root / "20260308T010101000001Z-comment.md").write_text(
        "---\nissue_id: 1\n---\n\nOrphan archive.\n",
        encoding="utf-8",
    )

    output_path = demo_repo / "tmp" / "sync-health.json"
    result = build_sync_health_report(
        loaded,
        cleanup_actions=[
            CleanAction(
                kind="artifacts",
                path=demo_repo / ".ai-repoagents" / "artifacts" / "issue-1" / "run-old",
                issue_id=1,
                run_id="run-old",
                state_updated=True,
            )
        ],
        issue_id=1,
        output_path=output_path,
        formats=("json", "markdown"),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    markdown = output_path.with_suffix(".md").read_text(encoding="utf-8")

    assert result.overall_status == "issues"
    assert result.pending_artifacts == 1
    assert result.integrity_issue_count == 1
    assert result.cleanup_action_count == 1
    assert any("repoagents sync repair --dry-run" in item for item in result.next_actions)
    assert payload["summary"]["overall_status"] == "issues"
    assert payload["summary"]["pending_artifacts"] == 1
    assert payload["summary"]["cleanup_action_count"] == 1
    assert payload["audit"]["summary"]["pending_artifacts"] == 1
    assert payload["check"]["summary"]["issues_with_findings"] == 1
    assert payload["repair_preview"]["summary"]["changed_reports"] == 1
    assert payload["cleanup_preview"]["summary"]["action_count"] == 1
    assert payload["related_reports"]["cleanup_reports"]["total_reports"] == 0
    assert payload["related_reports"]["sync_audit_reports"]["total_reports"] == 0
    assert "# RepoAgents Sync Health" in markdown
    assert "## Sync audit" in markdown
    assert "## Sync repair preview" in markdown
    assert "## Cleanup preview" in markdown


def test_build_sync_health_snapshot_surfaces_related_report_details(
    demo_repo: Path,
) -> None:
    _configure_policy_thresholds(demo_repo, threshold=2)
    reports_dir = demo_repo / ".ai-repoagents" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    _write_cleanup_preview_report(reports_dir, issue_filter=None)
    _write_cleanup_result_report(reports_dir, issue_filter=3)
    _write_sync_audit_report(reports_dir, issue_filter=None)
    loaded = load_config(demo_repo)

    snapshot = build_sync_health_snapshot(
        loaded,
        cleanup_actions=[],
        issue_id=1,
    )

    assert snapshot["summary"]["overall_status"] == "attention"
    assert snapshot["summary"]["related_report_mismatches"] == 1
    assert snapshot["summary"]["related_report_policy_drifts"] == 2
    assert any(
        "repoagents sync audit --format all" in item for item in snapshot["summary"]["next_actions"]
    )
    assert snapshot["related_reports"]["cleanup_reports"]["mismatch_reports"] == 1
    assert snapshot["related_reports"]["cleanup_reports"]["policy_drift_reports"] == 1
    assert "Cleanup preview" in snapshot["related_reports"]["cleanup_reports"]["detail_summary"]
    assert snapshot["related_reports"]["sync_audit_reports"]["mismatch_reports"] == 0
    assert snapshot["related_reports"]["sync_audit_reports"]["policy_drift_reports"] == 1
    assert "Sync audit" in snapshot["related_reports"]["sync_audit_reports"]["detail_summary"]


def _configure_policy_thresholds(repo_root: Path, *, threshold: int) -> None:
    config_path = repo_root / ".ai-repoagents" / "repoagents.yaml"
    payload = load_config(repo_root).data.model_dump(mode="json")
    payload.setdefault("dashboard", {})["report_freshness_policy"] = {
        "unknown_issues_threshold": threshold,
        "stale_issues_threshold": threshold,
        "future_attention_threshold": threshold,
        "aging_attention_threshold": threshold,
    }
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_cleanup_preview_report(reports_dir: Path, *, issue_filter: int | None) -> None:
    meta: dict[str, object] = {"rendered_at": "2026-03-08T05:00:00+00:00"}
    if issue_filter is not None:
        meta["issue_filter"] = issue_filter
    (reports_dir / "cleanup-preview.json").write_text(
        json.dumps(
            {
                "meta": meta,
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


def _write_cleanup_result_report(reports_dir: Path, *, issue_filter: int) -> None:
    (reports_dir / "cleanup-result.json").write_text(
        json.dumps(
            {
                "meta": {
                    "rendered_at": "2026-03-08T05:10:00+00:00",
                    "issue_filter": issue_filter,
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


def _write_sync_audit_report(reports_dir: Path, *, issue_filter: int | None) -> None:
    meta: dict[str, object] = {"rendered_at": "2026-03-08T05:00:00+00:00"}
    if issue_filter is not None:
        meta["issue_filter"] = issue_filter
    (reports_dir / "sync-audit.json").write_text(
        json.dumps(
            {
                "meta": meta,
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
