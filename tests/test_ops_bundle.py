from __future__ import annotations

import json
import tarfile
from pathlib import Path

from reporepublic.dashboard import DashboardBuildResult
from reporepublic.operator_reports import OperatorReportBuildResult
from reporepublic.ops_bundle import (
    build_ops_snapshot_archive,
    build_ops_snapshot_bundle,
    build_ops_snapshot_index,
    prune_ops_snapshot_history,
)
from reporepublic.sync_audit import SyncAuditBuildResult


def test_build_ops_snapshot_bundle_writes_manifest_and_combines_statuses(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "ops-bundle"
    doctor_json = bundle_dir / "doctor.json"
    doctor_md = bundle_dir / "doctor.md"
    status_json = bundle_dir / "status.json"
    status_md = bundle_dir / "status.md"
    dashboard_html = bundle_dir / "dashboard.html"
    dashboard_json = bundle_dir / "dashboard.json"
    dashboard_md = bundle_dir / "dashboard.md"
    sync_json = bundle_dir / "sync-audit.json"
    sync_md = bundle_dir / "sync-audit.md"

    for path in (doctor_json, doctor_md, status_json, status_md, dashboard_html, dashboard_md, sync_json, sync_md):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")
    dashboard_json.write_text(
        json.dumps(
            {
                "hero": {"severity": "attention"},
                "counts": {"available_reports": 3},
            }
        ),
        encoding="utf-8",
    )

    result = build_ops_snapshot_bundle(
        bundle_dir=bundle_dir,
        repo_root=tmp_path,
        config_path=tmp_path / ".ai-republic" / "reporepublic.yaml",
        issue_filter=7,
        tracker_filter="local-markdown",
        dashboard_limit=25,
        sync_limit=30,
        refresh_seconds=15,
        doctor_snapshot={
            "meta": {"rendered_at": "2026-03-09T10:00:00+00:00"},
            "summary": {"overall_status": "clean", "diagnostic_count": 5, "exit_code": 0},
        },
        doctor_result=OperatorReportBuildResult(
            output_paths={"json": doctor_json, "markdown": doctor_md},
            kind="doctor",
        ),
        status_snapshot={
            "summary": {"total_runs": 4, "selected_runs": 1},
            "report_health": {"hero": {"severity": "clean"}},
        },
        status_result=OperatorReportBuildResult(
            output_paths={"json": status_json, "markdown": status_md},
            kind="status",
        ),
        dashboard_result=DashboardBuildResult(
            output_path=dashboard_html,
            total_runs=4,
            visible_runs=4,
            exported_paths={"html": dashboard_html, "json": dashboard_json, "markdown": dashboard_md},
        ),
        sync_result=SyncAuditBuildResult(
            output_paths={"json": sync_json, "markdown": sync_md},
            overall_status="issues",
            pending_artifacts=2,
            integrity_issue_count=1,
            prunable_groups=0,
            related_cleanup_reports=1,
            cleanup_report_mismatches=0,
            cleanup_mismatch_warnings=(),
            related_cleanup_policy_drifts=0,
            cleanup_policy_drift_warnings=(),
            policy_drift_guidance=None,
        ),
    )

    manifest_json = bundle_dir / "bundle.json"
    manifest_md = bundle_dir / "bundle.md"
    payload = json.loads(manifest_json.read_text(encoding="utf-8"))

    assert result.overall_status == "issues"
    assert result.component_statuses == {
        "doctor": "clean",
        "status": "clean",
        "dashboard": "attention",
        "sync_audit": "issues",
    }
    assert manifest_json.exists()
    assert manifest_md.exists()
    assert payload["summary"]["overall_status"] == "issues"
    assert payload["summary"]["component_statuses"]["dashboard"] == "attention"
    assert payload["components"]["sync_audit"]["integrity_issue_count"] == 1
    assert payload["components"]["status"]["selected_runs"] == 1
    assert payload["components"]["dashboard"]["available_reports"] == 3
    assert "# RepoRepublic Ops Snapshot Bundle" in manifest_md.read_text(encoding="utf-8")


def test_build_ops_snapshot_bundle_includes_extra_components_and_cross_links(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "ops-bundle"
    sync_json = bundle_dir / "sync-audit.json"
    sync_md = bundle_dir / "sync-audit.md"
    doctor_json = bundle_dir / "doctor.json"
    doctor_md = bundle_dir / "doctor.md"
    status_json = bundle_dir / "status.json"
    status_md = bundle_dir / "status.md"
    dashboard_html = bundle_dir / "dashboard.html"
    dashboard_json = bundle_dir / "dashboard.json"
    dashboard_md = bundle_dir / "dashboard.md"
    cleanup_preview_json = bundle_dir / "cleanup-preview.json"
    cleanup_preview_md = bundle_dir / "cleanup-preview.md"
    cleanup_result_json = bundle_dir / "cleanup-result.json"
    cleanup_result_md = bundle_dir / "cleanup-result.md"
    sync_health_json = bundle_dir / "sync-health.json"
    sync_health_md = bundle_dir / "sync-health.md"
    ops_status_json = bundle_dir / "ops-status.json"
    ops_status_md = bundle_dir / "ops-status.md"

    for path in (
        sync_json,
        sync_md,
        doctor_json,
        doctor_md,
        status_json,
        status_md,
        dashboard_html,
        dashboard_json,
        dashboard_md,
        cleanup_preview_json,
        cleanup_preview_md,
        cleanup_result_json,
        cleanup_result_md,
        sync_health_json,
        sync_health_md,
        ops_status_json,
        ops_status_md,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            path.write_text("{}", encoding="utf-8")
        else:
            path.write_text("ok\n", encoding="utf-8")

    result = build_ops_snapshot_bundle(
        bundle_dir=bundle_dir,
        repo_root=tmp_path,
        config_path=tmp_path / ".ai-republic" / "reporepublic.yaml",
        issue_filter=None,
        tracker_filter=None,
        dashboard_limit=10,
        sync_limit=10,
        refresh_seconds=0,
        doctor_snapshot={"summary": {"overall_status": "clean", "diagnostic_count": 1, "exit_code": 0}},
        doctor_result=OperatorReportBuildResult(
            output_paths={"json": doctor_json, "markdown": doctor_md},
            kind="doctor",
        ),
        status_snapshot={
            "summary": {"total_runs": 2, "selected_runs": 2},
            "report_health": {"hero": {"severity": "clean"}},
        },
        status_result=OperatorReportBuildResult(
            output_paths={"json": status_json, "markdown": status_md},
            kind="status",
        ),
        dashboard_result=DashboardBuildResult(
            output_path=dashboard_html,
            total_runs=2,
            visible_runs=2,
            exported_paths={"html": dashboard_html, "json": dashboard_json, "markdown": dashboard_md},
        ),
        sync_result=SyncAuditBuildResult(
            output_paths={"json": sync_json, "markdown": sync_md},
            overall_status="ok",
            pending_artifacts=0,
            integrity_issue_count=0,
            prunable_groups=0,
            related_cleanup_reports=0,
            cleanup_report_mismatches=0,
            cleanup_mismatch_warnings=(),
            related_cleanup_policy_drifts=0,
            cleanup_policy_drift_warnings=(),
            policy_drift_guidance=None,
        ),
        extra_components={
            "cleanup_preview": {
                "status": "attention",
                "reason": "generated cleanup preview in ops snapshot bundle",
                "output_paths": {"json": cleanup_preview_json, "markdown": cleanup_preview_md},
                "mode": "preview",
                "action_count": 3,
                "link_to_sync_audit": True,
            },
            "cleanup_result": {
                "status": "clean",
                "reason": "copied existing cleanup result into ops snapshot bundle",
                "output_paths": {"json": cleanup_result_json, "markdown": cleanup_result_md},
                "mode": "applied",
                "action_count": 2,
                "link_to_sync_audit": True,
            },
            "sync_health": {
                "status": "attention",
                "reason": "generated sync health report in ops snapshot bundle",
                "output_paths": {"json": sync_health_json, "markdown": sync_health_md},
                "pending_artifacts": 1,
                "integrity_issue_count": 1,
                "repair_changed_reports": 1,
                "repair_findings_after": 0,
                "cleanup_action_count": 2,
                "related_report_mismatches": 1,
                "related_report_policy_drifts": 1,
                "next_action_count": 3,
                "link_targets": ("sync_audit", "cleanup_preview", "cleanup_result"),
            },
            "ops_status": {
                "status": "clean",
                "reason": "generated ops status report in ops snapshot bundle",
                "output_paths": {"json": ops_status_json, "markdown": ops_status_md},
                "history_entry_count": 1,
                "related_report_count": 1,
                "link_targets": ("sync_audit", "cleanup_preview"),
            },
        },
    )

    payload = json.loads((bundle_dir / "bundle.json").read_text(encoding="utf-8"))
    pairs = {(entry["source"], entry["target"]) for entry in payload["cross_links"]}
    assert result.component_statuses["cleanup_preview"] == "attention"
    assert result.component_statuses["cleanup_result"] == "clean"
    assert result.component_statuses["sync_health"] == "attention"
    assert result.component_statuses["ops_status"] == "clean"
    assert payload["components"]["cleanup_preview"]["mode"] == "preview"
    assert payload["components"]["cleanup_result"]["mode"] == "applied"
    assert payload["components"]["sync_health"]["repair_changed_reports"] == 1
    assert payload["components"]["ops_status"]["related_report_count"] == 1
    assert len(payload["cross_links"]) == 14
    assert ("sync_audit", "cleanup_preview") in pairs
    assert ("cleanup_preview", "sync_audit") in pairs
    assert ("sync_audit", "cleanup_result") in pairs
    assert ("cleanup_result", "sync_audit") in pairs
    assert ("sync_health", "sync_audit") in pairs
    assert ("sync_health", "cleanup_preview") in pairs
    assert ("sync_health", "cleanup_result") in pairs
    assert ("ops_status", "sync_audit") in pairs
    assert ("sync_audit", "ops_status") in pairs
    assert ("ops_status", "cleanup_preview") in pairs
    assert ("cleanup_preview", "ops_status") in pairs
    assert "cleanup-preview.json" in payload["components"]["cleanup_preview"]["output_paths"]["json"]
    assert "sync-health.json" in payload["components"]["sync_health"]["output_paths"]["json"]
    assert "ops-status.json" in payload["components"]["ops_status"]["output_paths"]["json"]


def test_build_ops_snapshot_bundle_links_sync_components_without_duplicates(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "ops-bundle"
    doctor_json = bundle_dir / "doctor.json"
    doctor_md = bundle_dir / "doctor.md"
    status_json = bundle_dir / "status.json"
    status_md = bundle_dir / "status.md"
    dashboard_html = bundle_dir / "dashboard.html"
    dashboard_json = bundle_dir / "dashboard.json"
    dashboard_md = bundle_dir / "dashboard.md"
    sync_json = bundle_dir / "sync-audit.json"
    sync_md = bundle_dir / "sync-audit.md"
    sync_check_json = bundle_dir / "sync-check.json"
    sync_check_md = bundle_dir / "sync-check.md"
    sync_repair_json = bundle_dir / "sync-repair-preview.json"
    sync_repair_md = bundle_dir / "sync-repair-preview.md"

    for path in (
        doctor_json,
        doctor_md,
        status_json,
        status_md,
        dashboard_html,
        dashboard_json,
        dashboard_md,
        sync_json,
        sync_md,
        sync_check_json,
        sync_check_md,
        sync_repair_json,
        sync_repair_md,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            path.write_text("{}", encoding="utf-8")
        else:
            path.write_text("ok\n", encoding="utf-8")

    build_ops_snapshot_bundle(
        bundle_dir=bundle_dir,
        repo_root=tmp_path,
        config_path=tmp_path / ".ai-republic" / "reporepublic.yaml",
        issue_filter=1,
        tracker_filter="local-markdown",
        dashboard_limit=10,
        sync_limit=10,
        refresh_seconds=0,
        doctor_snapshot={"summary": {"overall_status": "clean", "diagnostic_count": 1, "exit_code": 0}},
        doctor_result=OperatorReportBuildResult(
            output_paths={"json": doctor_json, "markdown": doctor_md},
            kind="doctor",
        ),
        status_snapshot={
            "summary": {"total_runs": 1, "selected_runs": 1},
            "report_health": {"hero": {"severity": "clean"}},
        },
        status_result=OperatorReportBuildResult(
            output_paths={"json": status_json, "markdown": status_md},
            kind="status",
        ),
        dashboard_result=DashboardBuildResult(
            output_path=dashboard_html,
            total_runs=1,
            visible_runs=1,
            exported_paths={"html": dashboard_html, "json": dashboard_json, "markdown": dashboard_md},
        ),
        sync_result=SyncAuditBuildResult(
            output_paths={"json": sync_json, "markdown": sync_md},
            overall_status="issues",
            pending_artifacts=0,
            integrity_issue_count=1,
            prunable_groups=0,
            related_cleanup_reports=0,
            cleanup_report_mismatches=0,
            cleanup_mismatch_warnings=(),
            related_cleanup_policy_drifts=0,
            cleanup_policy_drift_warnings=(),
            policy_drift_guidance=None,
        ),
        extra_components={
            "sync_check": {
                "status": "issues",
                "reason": "generated sync check report in ops snapshot bundle",
                "output_paths": {"json": sync_check_json, "markdown": sync_check_md},
                "report_count": 1,
                "issues_with_findings": 1,
                "total_findings": 2,
                "link_targets": ("sync_audit",),
            },
            "sync_repair_preview": {
                "status": "preview",
                "reason": "generated sync repair preview in ops snapshot bundle",
                "output_paths": {"json": sync_repair_json, "markdown": sync_repair_md},
                "mode": "preview",
                "report_count": 1,
                "changed_reports": 1,
                "findings_before": 2,
                "findings_after": 0,
                "adopted_archives": 1,
                "normalized_entries": 1,
                "link_targets": ("sync_audit", "sync_check"),
            },
        },
    )

    payload = json.loads((bundle_dir / "bundle.json").read_text(encoding="utf-8"))
    pairs = {(entry["source"], entry["target"]) for entry in payload["cross_links"]}

    assert payload["components"]["sync_check"]["issues_with_findings"] == 1
    assert payload["components"]["sync_repair_preview"]["changed_reports"] == 1
    assert ("sync_audit", "sync_check") in pairs
    assert ("sync_check", "sync_audit") in pairs
    assert ("sync_check", "sync_repair_preview") in pairs
    assert ("sync_repair_preview", "sync_check") in pairs
    assert len(payload["cross_links"]) == len(pairs)


def test_build_ops_snapshot_archive_creates_tarball_with_bundle_contents(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "ops-bundle"
    (bundle_dir / "bundle.json").parent.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "bundle.json").write_text('{"summary":{"overall_status":"clean"}}\n', encoding="utf-8")
    (bundle_dir / "bundle.md").write_text("# Bundle\n", encoding="utf-8")
    (bundle_dir / "sync-audit.json").write_text("{}\n", encoding="utf-8")

    result = build_ops_snapshot_archive(bundle_dir=bundle_dir)

    assert result.archive_path.exists()
    assert result.archive_path.name == "ops-bundle.tar.gz"
    assert result.file_count == 3
    assert result.member_count >= 4
    assert len(result.sha256) == 64
    with tarfile.open(result.archive_path, "r:gz") as bundle_archive:
        members = bundle_archive.getnames()
    assert "ops-bundle/bundle.json" in members
    assert "ops-bundle/bundle.md" in members
    assert "ops-bundle/sync-audit.json" in members


def test_build_ops_snapshot_index_tracks_latest_bundle_and_history(tmp_path: Path) -> None:
    ops_root = tmp_path / "reports" / "ops"
    bundle_one = ops_root / "20260309T100000Z"
    bundle_two = ops_root / "20260309T101500Z"

    def _write_bundle(bundle_dir: Path, *, rendered_at: str, overall_status: str) -> None:
        bundle_dir.mkdir(parents=True, exist_ok=True)
        (bundle_dir / "bundle.json").write_text(
            json.dumps(
                {
                    "meta": {
                        "rendered_at": rendered_at,
                        "bundle_dir": str(bundle_dir),
                        "issue_filter": 1,
                        "tracker_filter": "local-file",
                    },
                    "summary": {
                        "overall_status": overall_status,
                        "component_statuses": {"doctor": "clean", "sync_audit": overall_status},
                    },
                }
            ),
            encoding="utf-8",
        )
        (bundle_dir / "bundle.md").write_text("# Bundle\n", encoding="utf-8")

    _write_bundle(bundle_one, rendered_at="2026-03-09T10:00:00+00:00", overall_status="clean")
    first_bundle_result = build_ops_snapshot_bundle(
        bundle_dir=bundle_one,
        repo_root=tmp_path,
        config_path=tmp_path / ".ai-republic" / "reporepublic.yaml",
        issue_filter=1,
        tracker_filter="local-file",
        dashboard_limit=10,
        sync_limit=10,
        refresh_seconds=0,
        doctor_snapshot={"meta": {"rendered_at": "2026-03-09T10:00:00+00:00"}, "summary": {"overall_status": "clean", "diagnostic_count": 1, "exit_code": 0}},
        doctor_result=OperatorReportBuildResult(output_paths={}, kind="doctor"),
        status_snapshot={"summary": {"total_runs": 1, "selected_runs": 1}, "report_health": {"hero": {"severity": "clean"}}},
        status_result=OperatorReportBuildResult(output_paths={}, kind="status"),
        dashboard_result=DashboardBuildResult(output_path=bundle_one / "dashboard.html", total_runs=1, visible_runs=1, exported_paths={}),
        sync_result=SyncAuditBuildResult(
            output_paths={},
            overall_status="clean",
            pending_artifacts=0,
            integrity_issue_count=0,
            prunable_groups=0,
            related_cleanup_reports=0,
            cleanup_report_mismatches=0,
            cleanup_mismatch_warnings=(),
            related_cleanup_policy_drifts=0,
            cleanup_policy_drift_warnings=(),
            policy_drift_guidance=None,
        ),
    )
    first_index = build_ops_snapshot_index(ops_root=ops_root, bundle_result=first_bundle_result, history_limit=2)

    _write_bundle(bundle_two, rendered_at="2026-03-09T10:15:00+00:00", overall_status="issues")
    second_bundle_result = build_ops_snapshot_bundle(
        bundle_dir=bundle_two,
        repo_root=tmp_path,
        config_path=tmp_path / ".ai-republic" / "reporepublic.yaml",
        issue_filter=1,
        tracker_filter="local-file",
        dashboard_limit=10,
        sync_limit=10,
        refresh_seconds=0,
        doctor_snapshot={"meta": {"rendered_at": "2026-03-09T10:15:00+00:00"}, "summary": {"overall_status": "clean", "diagnostic_count": 1, "exit_code": 0}},
        doctor_result=OperatorReportBuildResult(output_paths={}, kind="doctor"),
        status_snapshot={"summary": {"total_runs": 1, "selected_runs": 1}, "report_health": {"hero": {"severity": "clean"}}},
        status_result=OperatorReportBuildResult(output_paths={}, kind="status"),
        dashboard_result=DashboardBuildResult(output_path=bundle_two / "dashboard.html", total_runs=1, visible_runs=1, exported_paths={}),
        sync_result=SyncAuditBuildResult(
            output_paths={},
            overall_status="issues",
            pending_artifacts=0,
            integrity_issue_count=1,
            prunable_groups=0,
            related_cleanup_reports=0,
            cleanup_report_mismatches=0,
            cleanup_mismatch_warnings=(),
            related_cleanup_policy_drifts=0,
            cleanup_policy_drift_warnings=(),
            policy_drift_guidance=None,
        ),
    )
    archive_result = build_ops_snapshot_archive(bundle_dir=bundle_two)
    second_index = build_ops_snapshot_index(
        ops_root=ops_root,
        bundle_result=second_bundle_result,
        archive_result=archive_result,
        history_limit=2,
    )

    latest_payload = json.loads(second_index.latest_json.read_text(encoding="utf-8"))
    history_payload = json.loads(second_index.history_json.read_text(encoding="utf-8"))
    history_markdown = second_index.history_markdown.read_text(encoding="utf-8")

    assert first_index.entry_count == 1
    assert first_index.history_limit == 2
    assert first_index.dropped_entries == ()
    assert second_index.entry_count == 2
    assert second_index.history_limit == 2
    assert second_index.dropped_entries == ()
    assert latest_payload["latest"]["entry_id"] == "20260309T101500Z"
    assert latest_payload["meta"]["history_limit"] == 2
    assert latest_payload["meta"]["dropped_entry_count"] == 0
    assert latest_payload["latest"]["archive"]["sha256"] == archive_result.sha256
    assert history_payload["latest_entry_id"] == "20260309T101500Z"
    assert history_payload["meta"]["dropped_entry_count"] == 0
    assert [entry["entry_id"] for entry in history_payload["entries"]] == [
        "20260309T101500Z",
        "20260309T100000Z",
    ]
    assert "## Entry 1" in history_markdown
    assert "archive:" in history_markdown


def test_build_ops_snapshot_index_preserves_additional_dropped_entries(tmp_path: Path) -> None:
    ops_root = tmp_path / "reports" / "ops"
    bundle_dir = ops_root / "20260309T101500Z"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "bundle.json").write_text(
        json.dumps(
            {
                "meta": {
                    "rendered_at": "2026-03-09T10:15:00+00:00",
                    "bundle_dir": str(bundle_dir),
                    "issue_filter": None,
                    "tracker_filter": None,
                },
                "summary": {
                    "overall_status": "clean",
                    "component_statuses": {"doctor": "clean", "sync_audit": "clean"},
                },
            }
        ),
        encoding="utf-8",
    )
    (bundle_dir / "bundle.md").write_text("# Bundle\n", encoding="utf-8")
    bundle_result = build_ops_snapshot_bundle(
        bundle_dir=bundle_dir,
        repo_root=tmp_path,
        config_path=tmp_path / ".ai-republic" / "reporepublic.yaml",
        issue_filter=None,
        tracker_filter=None,
        dashboard_limit=10,
        sync_limit=10,
        refresh_seconds=0,
        doctor_snapshot={"meta": {"rendered_at": "2026-03-09T10:15:00+00:00"}, "summary": {"overall_status": "clean", "diagnostic_count": 1, "exit_code": 0}},
        doctor_result=OperatorReportBuildResult(output_paths={}, kind="doctor"),
        status_snapshot={"summary": {"total_runs": 1, "selected_runs": 1}, "report_health": {"hero": {"severity": "clean"}}},
        status_result=OperatorReportBuildResult(output_paths={}, kind="status"),
        dashboard_result=DashboardBuildResult(output_path=bundle_dir / "dashboard.html", total_runs=1, visible_runs=1, exported_paths={}),
        sync_result=SyncAuditBuildResult(
            output_paths={},
            overall_status="clean",
            pending_artifacts=0,
            integrity_issue_count=0,
            prunable_groups=0,
            related_cleanup_reports=0,
            cleanup_report_mismatches=0,
            cleanup_mismatch_warnings=(),
            related_cleanup_policy_drifts=0,
            cleanup_policy_drift_warnings=(),
            policy_drift_guidance=None,
        ),
    )

    index_result = build_ops_snapshot_index(
        ops_root=ops_root,
        bundle_result=bundle_result,
        history_limit=1,
        additional_dropped_entries=(
            {
                "entry_id": "20260309T090000Z",
                "bundle_dir": str(ops_root / "20260309T090000Z"),
                "bundle_json": str(ops_root / "20260309T090000Z" / "bundle.json"),
            },
        ),
    )

    latest_payload = json.loads(index_result.latest_json.read_text(encoding="utf-8"))
    history_payload = json.loads(index_result.history_json.read_text(encoding="utf-8"))

    assert len(index_result.dropped_entries) == 1
    assert index_result.dropped_entries[0]["entry_id"] == "20260309T090000Z"
    assert latest_payload["meta"]["dropped_entry_count"] == 1
    assert history_payload["meta"]["dropped_entry_count"] == 1


def test_prune_ops_snapshot_history_removes_managed_dropped_entries_and_skips_external_paths(
    tmp_path: Path,
) -> None:
    ops_root = tmp_path / "reports" / "ops"
    active_bundle = ops_root / "20260309T101500Z"
    old_bundle = ops_root / "20260309T100000Z"
    external_bundle = tmp_path / "external-bundle"
    active_archive = ops_root / "20260309T101500Z.tar.gz"
    old_archive = ops_root / "20260309T100000Z.tar.gz"
    external_archive = tmp_path / "external-handoff.tar.gz"

    for bundle_dir in (active_bundle, old_bundle, external_bundle):
        bundle_dir.mkdir(parents=True, exist_ok=True)
        (bundle_dir / "bundle.json").write_text("{}\n", encoding="utf-8")
    for archive_path in (active_archive, old_archive, external_archive):
        archive_path.write_text("archive\n", encoding="utf-8")

    history_payload = {
        "meta": {
            "generated_at": "2026-03-09T10:15:00+00:00",
            "ops_root": str(ops_root),
            "history_limit": 1,
            "entry_count": 1,
            "dropped_entry_count": 2,
        },
        "latest_entry_id": "20260309T101500Z",
        "entries": [
            {
                "entry_id": "20260309T101500Z",
                "bundle_dir": str(active_bundle),
                "archive": {"path": str(active_archive)},
            }
        ],
    }
    ops_root.mkdir(parents=True, exist_ok=True)
    (ops_root / "history.json").write_text(json.dumps(history_payload), encoding="utf-8")

    prune_result = prune_ops_snapshot_history(
        ops_root=ops_root,
        dropped_entries=(
            {
                "entry_id": "20260309T100000Z",
                "bundle_dir": str(old_bundle),
                "archive": {"path": str(old_archive)},
            },
            {
                "entry_id": "external",
                "bundle_dir": str(external_bundle),
                "archive": {"path": str(external_archive)},
            },
        ),
    )

    assert not old_bundle.exists()
    assert not old_archive.exists()
    assert external_bundle.exists()
    assert external_archive.exists()
    assert active_bundle.exists()
    assert active_archive.exists()
    assert prune_result.removed_bundle_dirs == (old_bundle.resolve(),)
    assert prune_result.removed_archives == (old_archive.resolve(),)
    assert prune_result.skipped_external_paths == 2
    assert prune_result.skipped_active_paths == 0
    assert prune_result.missing_paths == 0
