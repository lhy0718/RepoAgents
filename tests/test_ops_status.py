from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from reporepublic.config import load_config
from reporepublic.ops_status import (
    build_ops_status_snapshot,
    render_ops_status_markdown,
)


def test_build_ops_status_snapshot_reads_latest_history_and_bundle_manifest(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "reporepublic.ops_status.utc_now",
        lambda: datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )
    _write_ops_snapshot_index(demo_repo)
    loaded = load_config(demo_repo)

    snapshot = build_ops_status_snapshot(loaded=loaded, history_preview_limit=2)

    assert snapshot["summary"]["status"] == "clean"
    assert snapshot["summary"]["index_status"] == "available"
    assert snapshot["summary"]["history_entry_count"] == 2
    assert snapshot["summary"]["related_report_count"] == 2
    assert snapshot["latest"]["entry_id"] == "20260309T101500Z"
    assert snapshot["latest"]["age_human"] == "1h 45m"
    assert snapshot["policy"]["summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert snapshot["related_reports"]["entries"][0]["key"] == "sync-audit"
    assert snapshot["related_reports"]["entries"][1]["key"] == "sync-health"
    assert snapshot["latest_bundle"]["status"] == "available"
    assert snapshot["latest_bundle"]["overall_status"] == "clean"
    assert snapshot["latest_bundle"]["component_count"] == 5
    assert snapshot["latest_bundle"]["cross_link_count"] == 2
    assert snapshot["latest_bundle"]["components"][0]["key"] == "dashboard"
    assert snapshot["latest_bundle"]["components"][1]["key"] == "doctor"
    assert snapshot["history"][1]["entry_id"] == "20260309T100000Z"
    assert snapshot["history"][1]["overall_status"] == "issues"


def test_render_ops_status_markdown_includes_latest_bundle_and_history(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "reporepublic.ops_status.utc_now",
        lambda: datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )
    _write_ops_snapshot_index(demo_repo)
    loaded = load_config(demo_repo)

    markdown = render_ops_status_markdown(
        build_ops_status_snapshot(loaded=loaded, history_preview_limit=2)
    )

    assert "# Ops snapshot status" in markdown
    assert "## Summary" in markdown
    assert "- status: clean" in markdown
    assert "## Policy" in markdown
    assert "- related_report_count: 2" in markdown
    assert "## Latest bundle manifest" in markdown
    assert "- component_count: 5" in markdown
    assert "### doctor" in markdown
    assert "- summary: diagnostic_count=5, exit_code=0" in markdown
    assert "## Bundle cross links" in markdown
    assert "- sync_audit -> cleanup_preview" in markdown
    assert "## Related reports" in markdown
    assert "- Sync audit" in markdown
    assert "- Sync health" in markdown
    assert "## History preview" in markdown
    assert "- entry_id: 20260309T100000Z" in markdown


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
                "sync_health": "attention",
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
            "sync_health": {
                "status": "attention",
                "output_paths": {
                    "json": str(latest_bundle_dir / "sync-health.json"),
                    "markdown": str(latest_bundle_dir / "sync-health.md"),
                },
                "pending_artifacts": 1,
                "integrity_issue_count": 1,
                "repair_changed_reports": 1,
                "cleanup_action_count": 2,
                "related_report_mismatches": 1,
                "related_report_policy_drifts": 1,
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
            "issue_filter": 1,
            "tracker_filter": "local-file",
            "bundle_dir": str(latest_bundle_dir),
            "bundle_relative_dir": "20260309T101500Z",
            "bundle_json": str(latest_bundle_dir / "bundle.json"),
            "bundle_markdown": str(latest_bundle_dir / "bundle.md"),
            "archive": {
                "path": str(ops_root / "20260309T101500Z.tar.gz"),
                "relative_path": "20260309T101500Z.tar.gz",
                "sha256": "a" * 64,
                "size_bytes": 1234,
                "file_count": 8,
                "member_count": 10,
            },
            "component_statuses": {
                "doctor": "clean",
                "dashboard": "clean",
                "status": "clean",
                "sync_audit": "attention",
                "sync_health": "attention",
            },
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
                "issue_filter": None,
                "tracker_filter": None,
                "bundle_dir": str(previous_bundle_dir),
                "bundle_relative_dir": "20260309T100000Z",
                "bundle_json": str(previous_bundle_dir / "bundle.json"),
                "bundle_markdown": str(previous_bundle_dir / "bundle.md"),
                "archive": None,
                "component_statuses": {"doctor": "clean", "dashboard": "issues"},
            },
        ],
    }
    (ops_root / "latest.json").write_text(
        json.dumps(latest_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (ops_root / "latest.md").write_text("# Latest ops\n", encoding="utf-8")
    (ops_root / "history.json").write_text(
        json.dumps(history_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (ops_root / "history.md").write_text("# Ops history\n", encoding="utf-8")
