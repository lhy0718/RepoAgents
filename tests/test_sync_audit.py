from __future__ import annotations

import json
from pathlib import Path

import yaml

from reporepublic.config import load_config
from reporepublic.sync_audit import build_sync_audit_report, build_sync_audit_snapshot


def test_build_sync_audit_report_writes_json_and_markdown_exports(demo_repo: Path) -> None:
    _configure_sync_retention(demo_repo, keep_groups=1)
    loaded = load_config(demo_repo)
    _write_cleanup_reports(demo_repo)

    pending_dir = loaded.sync_dir / "local-file" / "issue-1"
    pending_dir.mkdir(parents=True, exist_ok=True)
    (pending_dir / "20260308T020101000001Z-comment.md").write_text(
        "---\nissue_id: 1\nstaged_at: 20260308T020101000001Z\n---\n\nPending maintainer note.\n",
        encoding="utf-8",
    )

    applied_root = loaded.sync_applied_dir / "local-file" / "issue-1"
    applied_root.mkdir(parents=True, exist_ok=True)
    older_branch = applied_root / "20260308T010001000001Z-branch.json"
    newer_comment = applied_root / "20260308T010101000001Z-comment.md"
    older_branch.write_text(
        json.dumps(
            {
                "action": "branch",
                "issue_id": 1,
                "branch_name": "reporepublic/issue-1-older",
                "staged_at": "20260308T010001000001Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    newer_comment.write_text("---\nissue_id: 1\n---\n\nRecent comment handoff.\n", encoding="utf-8")
    (applied_root / "manifest.json").write_text(
        json.dumps(
            [
                _manifest_entry(
                    tracker="local-file",
                    issue_id=1,
                    action="branch",
                    applied_at="2026-03-08T01:00:01+00:00",
                    staged_at="20260308T010001000001Z",
                    archived_path=older_branch,
                    group_key="issue:1|head:reporepublic/issue-1-older",
                    artifact_role="branch-proposal",
                ),
                _manifest_entry(
                    tracker="local-file",
                    issue_id=1,
                    action="comment",
                    applied_at="2026-03-08T01:01:01+00:00",
                    staged_at="20260308T010101000001Z",
                    archived_path=newer_comment,
                    group_key="issue:1|comment",
                    artifact_role="comment-proposal",
                ),
            ],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = build_sync_audit_report(loaded, formats=("json", "markdown"))
    payload = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
    markdown = result.output_paths["markdown"].read_text(encoding="utf-8")

    assert result.output_paths["json"].exists()
    assert result.output_paths["markdown"].exists()
    assert result.overall_status == "attention"
    assert result.related_cleanup_reports == 2
    assert result.related_cleanup_policy_drifts == 0
    assert payload["policy"]["summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert payload["policy"]["report_freshness_policy"]["stale_issues_threshold"] == 1
    assert payload["summary"]["pending_artifacts"] == 1
    assert payload["summary"]["integrity_issue_count"] == 0
    assert payload["summary"]["prunable_groups"] == 1
    assert payload["summary"]["related_cleanup_reports"] == 2
    assert payload["related_reports"]["entries"][0]["label"] == "Cleanup preview"
    assert payload["related_reports"]["entries"][1]["label"] == "Cleanup result"
    assert payload["retention"]["entries"][0]["status"] == "prunable"
    assert "# RepoRepublic Sync Audit" in markdown
    assert "## Policy" in markdown
    assert "- report_freshness_policy: unknown>=1 stale>=1 future>=1 aging>=1" in markdown
    assert "## Pending staged artifacts" in markdown
    assert "## Applied retention" in markdown
    assert "## Related cleanup reports" in markdown
    assert "- policy_drift_guidance: n/a" in markdown
    assert "### Cleanup result" in markdown


def test_build_sync_audit_snapshot_filters_related_cleanup_reports_by_issue(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    _write_cleanup_reports(
        demo_repo,
        preview_issue_filter=3,
        result_issue_filter=7,
    )

    snapshot = build_sync_audit_snapshot(loaded, issue_id=7)

    assert snapshot["summary"]["related_cleanup_reports"] == 1
    assert snapshot["summary"]["cleanup_report_mismatches"] == 1
    assert [entry["label"] for entry in snapshot["related_reports"]["entries"]] == ["Cleanup result"]
    assert [entry["label"] for entry in snapshot["related_reports"]["mismatches"]] == ["Cleanup preview"]
    assert "issue_filter=3 does not match audit issue_filter=7" in snapshot["related_reports"]["mismatches"][0]["warning"]


def test_build_sync_audit_snapshot_reports_integrity_issues(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    applied_root = loaded.sync_applied_dir / "local-markdown" / "issue-9"
    applied_root.mkdir(parents=True, exist_ok=True)
    orphan = applied_root / "20260308T030101000001Z-comment.md"
    orphan.write_text("---\nissue_id: 9\n---\n\nOrphan archive.\n", encoding="utf-8")

    snapshot = build_sync_audit_snapshot(loaded, issue_id=9, tracker="local-markdown")

    assert snapshot["policy"]["summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert snapshot["summary"]["overall_status"] == "issues"
    assert snapshot["summary"]["integrity_issue_count"] == 1
    assert snapshot["integrity"]["finding_counts"]["missing_manifest"] == 1
    assert snapshot["retention"]["repair_needed_issues"] == 1
    assert snapshot["retention"]["entries"][0]["status"] == "repair-needed"


def test_build_sync_audit_snapshot_cross_links_cleanup_policy_drift(demo_repo: Path) -> None:
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
    _write_cleanup_reports(demo_repo)
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
    loaded = load_config(demo_repo)

    snapshot = build_sync_audit_snapshot(loaded)
    markdown = build_sync_audit_report(loaded, formats=("markdown",)).output_paths["markdown"].read_text(
        encoding="utf-8"
    )

    assert snapshot["summary"]["related_cleanup_policy_drifts"] == 1
    assert snapshot["related_reports"]["policy_drift_reports"] == 1
    assert (
        snapshot["related_reports"]["policy_drift_guidance"]
        == "refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert snapshot["related_reports"]["policy_drifts"][0]["label"] == "Cleanup preview"
    assert (
        snapshot["related_reports"]["policy_drifts"][0]["remediation"]
        == "refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert snapshot["related_reports"]["entries"][0]["policy_alignment"]["status"] == "drift"
    assert (
        snapshot["related_reports"]["entries"][0]["policy_alignment"]["remediation"]
        == "refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`"
    )
    assert (
        snapshot["related_reports"]["entries"][0]["policy_alignment"]["embedded_summary"]
        == "unknown>=1 stale>=1 future>=1 aging>=1"
    )
    assert "### Cleanup report policy drifts" in markdown
    assert "- policy_alignment: drift" in markdown
    assert "- embedded_policy: unknown>=1 stale>=1 future>=1 aging>=1" in markdown
    assert "- policy_drift_guidance: refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`" in markdown
    assert "- policy_remediation: refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`" in markdown
    assert "- remediation: refresh raw report exports to align embedded policy metadata; re-run `republic sync audit --format all` and `republic clean --report --report-format all` after updating `dashboard.report_freshness_policy`" in markdown


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


def _write_cleanup_reports(
    repo_root: Path,
    *,
    preview_issue_filter: int | None = None,
    result_issue_filter: int | None = None,
    cleanup_result: bool = True,
) -> None:
    reports_dir = repo_root / ".ai-republic" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "cleanup-preview.json").write_text(
        json.dumps(
            {
                "meta": {
                    "rendered_at": "2026-03-08T04:10:00+00:00",
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
    if cleanup_result:
        (reports_dir / "cleanup-result.json").write_text(
            json.dumps(
                {
                    "meta": {
                        "rendered_at": "2026-03-08T04:20:00+00:00",
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
