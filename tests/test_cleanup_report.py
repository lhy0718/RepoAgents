from __future__ import annotations

import json
from pathlib import Path

from reporepublic.cleanup_report import build_cleanup_report
from reporepublic.config import load_config


def test_build_cleanup_report_writes_preview_exports(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    report_path = demo_repo / ".ai-republic" / "reports" / "custom-cleanup.json"

    result = build_cleanup_report(
        loaded,
        actions=[],
        dry_run=True,
        include_sync_applied=True,
        issue_id=1,
        sync_keep_groups_per_issue=5,
        output_path=report_path,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
    markdown = result.output_paths["markdown"].read_text(encoding="utf-8")

    assert result.mode == "preview"
    assert result.action_count == 0
    assert result.related_sync_audit_reports == 0
    assert result.sync_audit_issue_filter_mismatches == 0
    assert result.sync_audit_policy_drifts == 0
    assert payload["meta"]["mode"] == "preview"
    assert payload["policy"]["summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert payload["policy"]["report_freshness_policy"]["future_attention_threshold"] == 1
    assert payload["summary"]["overall_status"] == "clean"
    assert payload["related_reports"]["detail_summary"] is None
    assert "# RepoRepublic Cleanup Report" in markdown
    assert "## Policy" in markdown
    assert "- report_freshness_policy: unknown>=1 stale>=1 future>=1 aging>=1" in markdown
    assert "- policy_drift_guidance: n/a" in markdown
    assert "No cleanup actions were generated." in markdown


def test_build_cleanup_report_cross_links_sync_audit_policy_drift(demo_repo: Path) -> None:
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
    loaded = load_config(demo_repo)

    result = build_cleanup_report(
        loaded,
        actions=[],
        dry_run=True,
        include_sync_applied=True,
        issue_id=1,
        sync_keep_groups_per_issue=5,
        formats=("json", "markdown"),
    )
    payload = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
    markdown = result.output_paths["markdown"].read_text(encoding="utf-8")

    assert payload["summary"]["related_sync_audit_reports"] == 1
    assert payload["summary"]["sync_audit_issue_filter_mismatches"] == 0
    assert payload["summary"]["sync_audit_policy_drifts"] == 1
    assert payload["related_reports"]["policy_drift_reports"] == 1
    assert (
        payload["related_reports"]["policy_drift_guidance"]
        == "refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert payload["related_reports"]["entries"][0]["label"] == "Sync audit"
    assert payload["related_reports"]["entries"][0]["policy_alignment"]["status"] == "drift"
    assert (
        payload["related_reports"]["entries"][0]["policy_alignment"]["remediation"]
        == "refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert (
        payload["related_reports"]["detail_summary"]
        == "related report details\n"
        "policy drifts\n"
        "- Sync audit: embedded policy differs from current config (unknown>=1 stale>=1 future>=1 aging>=1)\n"
        "remediation: refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert (
        payload["related_reports"]["entries"][0]["policy_alignment"]["embedded_summary"]
        == "unknown>=1 stale>=1 future>=1 aging>=1"
    )
    assert "## Related reports" in markdown
    assert "### Sync audit" in markdown
    assert "### Sync audit policy drifts" in markdown
    assert "- policy_alignment: drift" in markdown
    assert "- policy_drift_guidance: refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`" in markdown
    assert "- policy_remediation: refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`" in markdown
    assert "- remediation: refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`" in markdown
