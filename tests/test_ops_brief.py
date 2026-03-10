from __future__ import annotations

import json
from pathlib import Path

from repoagents.ops_brief import build_ops_brief_exports, build_ops_brief_snapshot


def test_build_ops_brief_snapshot_summarizes_findings_and_actions(tmp_path: Path) -> None:
    snapshot = build_ops_brief_snapshot(
        repo_root=tmp_path,
        config_path=tmp_path / ".ai-repoagents" / "repoagents.yaml",
        issue_filter=7,
        tracker_filter="local-file",
        doctor_snapshot={
            "summary": {"overall_status": "clean", "diagnostic_count": 5, "exit_code": 0},
        },
        status_snapshot={
            "summary": {"total_runs": 4, "selected_runs": 1},
            "report_health": {
                "hero": {
                    "severity": "attention",
                    "title": "Report freshness needs follow-up",
                    "summary": "stale reports are below the issue threshold but should be refreshed",
                }
            },
        },
        dashboard_snapshot={"hero": {"severity": "attention"}, "reports": {"entries": [1, 2, 3]}},
        sync_audit_snapshot={
            "summary": {
                "overall_status": "issues",
                "pending_artifacts": 2,
                "integrity_issue_count": 1,
                "repair_needed_issues": 1,
            }
        },
        sync_health_snapshot={
            "summary": {
                "overall_status": "issues",
                "pending_artifacts": 2,
                "integrity_issue_count": 1,
                "repair_changed_reports": 1,
                "cleanup_action_count": 3,
                "related_report_policy_drifts": 1,
                "next_actions": [
                    "Run `repoagents sync repair --dry-run --issue 7`.",
                    "Review cleanup preview before pruning.",
                ],
            }
        },
    )

    assert snapshot["summary"]["severity"] == "issues"
    assert snapshot["summary"]["top_finding_count"] >= 3
    assert snapshot["summary"]["next_action_count"] == 3
    assert snapshot["policy"]["summary"] is None
    assert snapshot["related_reports"]["entries"][0]["key"] == "ops-status"
    assert snapshot["related_reports"]["entries"][1]["key"] == "sync-audit"
    assert snapshot["related_reports"]["entries"][2]["key"] == "sync-health"
    assert snapshot["top_findings"][0] == "Report health: Report freshness needs follow-up."
    assert "Sync health found 2 pending staged artifact(s)." in snapshot["top_findings"]
    assert "Run `repoagents sync repair --dry-run --issue 7`." in snapshot["next_actions"]


def test_build_ops_brief_exports_writes_json_and_markdown(tmp_path: Path) -> None:
    snapshot = build_ops_brief_snapshot(
        repo_root=tmp_path,
        config_path=tmp_path / ".ai-repoagents" / "repoagents.yaml",
        issue_filter=None,
        tracker_filter=None,
        doctor_snapshot={"summary": {"overall_status": "clean", "diagnostic_count": 2, "exit_code": 0}},
        status_snapshot={
            "summary": {"total_runs": 1, "selected_runs": 1},
            "report_health": {"hero": {"severity": "clean", "title": "All clear", "summary": "clean"}},
        },
        dashboard_snapshot={"hero": {"severity": "clean"}, "reports": {"entries": []}},
        sync_audit_snapshot={
            "summary": {
                "overall_status": "clean",
                "pending_artifacts": 0,
                "integrity_issue_count": 0,
                "repair_needed_issues": 0,
            }
        },
        sync_health_snapshot={
            "summary": {
                "overall_status": "clean",
                "pending_artifacts": 0,
                "integrity_issue_count": 0,
                "repair_changed_reports": 0,
                "cleanup_action_count": 0,
                "related_report_policy_drifts": 0,
                "next_actions": [],
            }
        },
    )

    result = build_ops_brief_exports(
        snapshot=snapshot,
        output_path=tmp_path / "ops-brief.json",
        formats=("json", "markdown"),
    )

    payload = json.loads((tmp_path / "ops-brief.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "ops-brief.md").read_text(encoding="utf-8")

    assert result.severity == "clean"
    assert result.headline == "Current ops snapshot is clean and ready to hand off."
    assert payload["summary"]["severity"] == "clean"
    assert payload["summary"]["top_finding_count"] == 0
    assert payload["related_reports"]["entries"][0]["key"] == "ops-status"
    assert "# RepoAgents Ops Brief" in markdown
    assert "## Policy" in markdown
    assert "## Related reports" in markdown
    assert "- headline: Current ops snapshot is clean and ready to hand off." in markdown


def test_build_ops_brief_snapshot_includes_github_smoke_signal(tmp_path: Path) -> None:
    snapshot = build_ops_brief_snapshot(
        repo_root=tmp_path,
        config_path=tmp_path / ".ai-repoagents" / "repoagents.yaml",
        issue_filter=7,
        tracker_filter="github",
        doctor_snapshot={"summary": {"overall_status": "clean", "diagnostic_count": 2, "exit_code": 0}},
        status_snapshot={
            "summary": {"total_runs": 1, "selected_runs": 1},
            "report_health": {"hero": {"severity": "clean", "title": "All clear", "summary": "clean"}},
        },
        dashboard_snapshot={"hero": {"severity": "clean"}, "reports": {"entries": []}},
        sync_audit_snapshot={
            "summary": {
                "overall_status": "clean",
                "pending_artifacts": 0,
                "integrity_issue_count": 0,
                "repair_needed_issues": 0,
            }
        },
        sync_health_snapshot={
            "summary": {
                "overall_status": "clean",
                "pending_artifacts": 0,
                "integrity_issue_count": 0,
                "repair_changed_reports": 0,
                "cleanup_action_count": 0,
                "related_report_policy_drifts": 0,
                "next_actions": [],
            }
        },
        github_smoke_snapshot={
            "summary": {
                "status": "attention",
                "message": "branch policy: default branch main is not protected",
                "open_issue_count": 2,
                "sampled_issue_id": 7,
            },
            "publish": {
                "status": "warn",
                "message": "branch policy: default branch main is not protected",
            },
            "branch_policy": {
                "status": "warn",
                "message": "default branch main is not protected",
            },
        },
    )

    assert snapshot["summary"]["severity"] == "attention"
    assert snapshot["summary"]["github_smoke_status"] == "attention"
    assert snapshot["related_reports"]["entries"][-1]["key"] == "github-smoke"
    assert "GitHub publish readiness: branch policy: default branch main is not protected." in snapshot["top_findings"]
    assert any("repoagents github smoke --require-write-ready" in item for item in snapshot["next_actions"])
