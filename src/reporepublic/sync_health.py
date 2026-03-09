from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from reporepublic._related_report_details.rendering import (
    build_related_report_detail_summary,
    extract_related_report_warning_lines,
)
from reporepublic.cleanup_report import build_cleanup_report_snapshot
from reporepublic.config import LoadedConfig
from reporepublic.models.domain import utc_now
from reporepublic.sync_audit import build_sync_audit_snapshot
from reporepublic.sync_manifest_reports import (
    build_sync_check_snapshot,
    build_sync_repair_snapshot,
)
from reporepublic.utils.files import write_text_file


VALID_SYNC_HEALTH_FORMATS = ("json", "markdown")


@dataclass(frozen=True, slots=True)
class SyncHealthBuildResult:
    output_paths: dict[str, Path]
    snapshot: dict[str, Any]
    overall_status: str
    pending_artifacts: int
    integrity_issue_count: int
    repair_changed_reports: int
    repair_findings_after: int
    cleanup_action_count: int
    next_actions: tuple[str, ...]
    related_cleanup_reports: int
    related_cleanup_mismatch_warnings: tuple[str, ...]
    related_cleanup_policy_drift_warnings: tuple[str, ...]
    related_cleanup_policy_drift_guidance: str | None
    related_sync_audit_reports: int
    related_sync_audit_mismatch_warnings: tuple[str, ...]
    related_sync_audit_policy_drift_warnings: tuple[str, ...]
    related_sync_audit_policy_drift_guidance: str | None


def normalize_sync_health_formats(
    formats: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if not formats:
        return ("json",)
    normalized: list[str] = []
    for value in formats:
        lowered = value.strip().lower()
        if not lowered:
            continue
        if lowered == "all":
            for item in VALID_SYNC_HEALTH_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_SYNC_HEALTH_FORMATS:
            raise ValueError("Unsupported sync health format. Expected one of: json, markdown, all")
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def resolve_sync_health_export_paths(
    target: Path,
    formats: tuple[str, ...],
) -> dict[str, Path]:
    export_paths: dict[str, Path] = {}
    resolved = target.resolve()
    for export_format in formats:
        suffix = ".md" if export_format == "markdown" else ".json"
        export_paths[export_format] = resolved.with_suffix(suffix)
    return export_paths


def build_sync_health_report(
    loaded: LoadedConfig,
    *,
    cleanup_actions: Sequence[object],
    issue_id: int | None = None,
    tracker: str | None = None,
    limit: int = 50,
    cleanup_include_sync_applied: bool = True,
    cleanup_keep_groups_per_issue: int | None = None,
    output_path: Path | None = None,
    formats: tuple[str, ...] = ("json", "markdown"),
) -> SyncHealthBuildResult:
    normalized_formats = normalize_sync_health_formats(formats)
    target = output_path or (loaded.reports_dir / "sync-health.json")
    export_paths = resolve_sync_health_export_paths(target, normalized_formats)
    snapshot = build_sync_health_snapshot(
        loaded,
        cleanup_actions=cleanup_actions,
        issue_id=issue_id,
        tracker=tracker,
        limit=limit,
        cleanup_include_sync_applied=cleanup_include_sync_applied,
        cleanup_keep_groups_per_issue=cleanup_keep_groups_per_issue,
    )
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_sync_health_json(snapshot))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_sync_health_markdown(snapshot))

    summary = _mapping(snapshot, "summary")
    related_reports = _mapping(snapshot, "related_reports")
    cleanup_reports = _mapping(related_reports, "cleanup_reports")
    sync_audit_reports = _mapping(related_reports, "sync_audit_reports")
    return SyncHealthBuildResult(
        output_paths=export_paths,
        snapshot=snapshot,
        overall_status=str(summary.get("overall_status", "clean")),
        pending_artifacts=int(summary.get("pending_artifacts", 0)),
        integrity_issue_count=int(summary.get("integrity_issue_count", 0)),
        repair_changed_reports=int(summary.get("repair_changed_reports", 0)),
        repair_findings_after=int(summary.get("repair_findings_after", 0)),
        cleanup_action_count=int(summary.get("cleanup_action_count", 0)),
        next_actions=tuple(str(item) for item in _list_of_strings(summary.get("next_actions"))),
        related_cleanup_reports=int(cleanup_reports.get("total_reports", 0)),
        related_cleanup_mismatch_warnings=extract_related_report_warning_lines(
            cleanup_reports.get("mismatches")
        ),
        related_cleanup_policy_drift_warnings=extract_related_report_warning_lines(
            cleanup_reports.get("policy_drifts")
        ),
        related_cleanup_policy_drift_guidance=_string_or_none(
            cleanup_reports.get("policy_drift_guidance")
        ),
        related_sync_audit_reports=int(sync_audit_reports.get("total_reports", 0)),
        related_sync_audit_mismatch_warnings=extract_related_report_warning_lines(
            sync_audit_reports.get("mismatches")
        ),
        related_sync_audit_policy_drift_warnings=extract_related_report_warning_lines(
            sync_audit_reports.get("policy_drifts")
        ),
        related_sync_audit_policy_drift_guidance=_string_or_none(
            sync_audit_reports.get("policy_drift_guidance")
        ),
    )


def build_sync_health_snapshot(
    loaded: LoadedConfig,
    *,
    cleanup_actions: Sequence[object],
    issue_id: int | None = None,
    tracker: str | None = None,
    limit: int = 50,
    cleanup_include_sync_applied: bool = True,
    cleanup_keep_groups_per_issue: int | None = None,
) -> dict[str, Any]:
    audit = build_sync_audit_snapshot(
        loaded,
        issue_id=issue_id,
        tracker=tracker,
        limit=limit,
    )
    check = build_sync_check_snapshot(
        loaded,
        issue_id=issue_id,
        tracker=tracker,
    )
    repair_preview = build_sync_repair_snapshot(
        loaded,
        dry_run=True,
        issue_id=issue_id,
        tracker=tracker,
    )
    cleanup_preview = build_cleanup_report_snapshot(
        loaded,
        actions=list(cleanup_actions),
        dry_run=True,
        include_sync_applied=cleanup_include_sync_applied,
        issue_id=issue_id,
        sync_keep_groups_per_issue=cleanup_keep_groups_per_issue if cleanup_include_sync_applied else None,
    )

    audit_summary = _mapping(audit, "summary")
    check_summary = _mapping(check, "summary")
    repair_summary = _mapping(repair_preview, "summary")
    cleanup_summary = _mapping(cleanup_preview, "summary")

    related_reports = {
        "cleanup_reports": _serialize_related_report_group(_mapping(audit, "related_reports")),
        "sync_audit_reports": _serialize_related_report_group(_mapping(cleanup_preview, "related_reports")),
    }
    summary = _build_sync_health_summary(
        audit_summary=audit_summary,
        check_summary=check_summary,
        repair_summary=repair_summary,
        cleanup_summary=cleanup_summary,
        related_reports=related_reports,
    )

    return {
        "meta": {
            "rendered_at": utc_now().isoformat(),
            "repo_root": str(loaded.repo_root),
            "config_path": str(loaded.config_path),
            "issue_filter": issue_id,
            "tracker_filter": tracker,
            "limit": limit,
            "cleanup_include_sync_applied": cleanup_include_sync_applied,
            "cleanup_keep_groups_per_issue": cleanup_keep_groups_per_issue if cleanup_include_sync_applied else None,
        },
        "policy": _mapping(audit, "policy"),
        "summary": summary,
        "related_reports": related_reports,
        "audit": audit,
        "check": check,
        "repair_preview": repair_preview,
        "cleanup_preview": cleanup_preview,
    }


def render_sync_health_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


def render_sync_health_markdown(snapshot: dict[str, Any]) -> str:
    meta = _mapping(snapshot, "meta")
    policy = _mapping(snapshot, "policy")
    summary = _mapping(snapshot, "summary")
    related_reports = _mapping(snapshot, "related_reports")
    audit_summary = _mapping(_mapping(snapshot, "audit"), "summary")
    check_summary = _mapping(_mapping(snapshot, "check"), "summary")
    repair_summary = _mapping(_mapping(snapshot, "repair_preview"), "summary")
    cleanup_summary = _mapping(_mapping(snapshot, "cleanup_preview"), "summary")
    cleanup_reports = _mapping(related_reports, "cleanup_reports")
    sync_audit_reports = _mapping(related_reports, "sync_audit_reports")

    lines = [
        "# RepoRepublic Sync Health",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- config_path: {meta.get('config_path', '-')}",
        f"- issue_filter: {meta.get('issue_filter') if meta.get('issue_filter') is not None else 'all'}",
        f"- tracker_filter: {meta.get('tracker_filter') or 'all'}",
        f"- limit: {meta.get('limit', 0)}",
        f"- cleanup_include_sync_applied: {meta.get('cleanup_include_sync_applied', False)}",
        f"- cleanup_keep_groups_per_issue: {meta.get('cleanup_keep_groups_per_issue') if meta.get('cleanup_keep_groups_per_issue') is not None else 'n/a'}",
        "",
        "## Policy",
        f"- report_freshness_policy: {policy.get('summary', 'n/a')}",
        "",
        "## Summary",
        f"- overall_status: {summary.get('overall_status', '-')}",
        f"- pending_artifacts: {summary.get('pending_artifacts', 0)}",
        f"- integrity_issue_count: {summary.get('integrity_issue_count', 0)}",
        f"- repair_changed_reports: {summary.get('repair_changed_reports', 0)}",
        f"- repair_findings_after: {summary.get('repair_findings_after', 0)}",
        f"- cleanup_action_count: {summary.get('cleanup_action_count', 0)}",
        f"- cleanup_sync_applied_action_count: {summary.get('cleanup_sync_applied_action_count', 0)}",
        f"- related_report_mismatches: {summary.get('related_report_mismatches', 0)}",
        f"- related_report_policy_drifts: {summary.get('related_report_policy_drifts', 0)}",
        "",
        "## Next actions",
    ]
    next_actions = _list_of_strings(summary.get("next_actions"))
    if next_actions:
        lines.extend(f"- {item}" for item in next_actions)
    else:
        lines.append("- No follow-up actions suggested.")

    lines.extend(
        [
            "",
            "## Sync audit",
            f"- overall_status: {audit_summary.get('overall_status', '-')}",
            f"- pending_artifacts: {audit_summary.get('pending_artifacts', 0)}",
            f"- integrity_issue_count: {audit_summary.get('integrity_issue_count', 0)}",
            f"- prunable_groups: {audit_summary.get('prunable_groups', 0)}",
            f"- repair_needed_issues: {audit_summary.get('repair_needed_issues', 0)}",
            f"- related_cleanup_reports: {audit_summary.get('related_cleanup_reports', 0)}",
            "",
            "## Sync check",
            f"- overall_status: {check_summary.get('overall_status', '-')}",
            f"- total_reports: {check_summary.get('total_reports', 0)}",
            f"- issues_with_findings: {check_summary.get('issues_with_findings', 0)}",
            f"- total_findings: {check_summary.get('total_findings', 0)}",
            f"- finding_counts: {_render_mapping(check_summary.get('finding_counts'))}",
            "",
            "## Sync repair preview",
            f"- overall_status: {repair_summary.get('overall_status', '-')}",
            f"- total_reports: {repair_summary.get('total_reports', 0)}",
            f"- changed_reports: {repair_summary.get('changed_reports', 0)}",
            f"- findings_before: {repair_summary.get('findings_before', 0)}",
            f"- findings_after: {repair_summary.get('findings_after', 0)}",
            "",
            "## Cleanup preview",
            f"- overall_status: {cleanup_summary.get('overall_status', '-')}",
            f"- action_count: {cleanup_summary.get('action_count', 0)}",
            f"- affected_issue_count: {cleanup_summary.get('affected_issue_count', 0)}",
            f"- sync_applied_action_count: {cleanup_summary.get('sync_applied_action_count', 0)}",
            f"- related_sync_audit_reports: {cleanup_summary.get('related_sync_audit_reports', 0)}",
            "",
            "## Related cleanup reports",
            f"- total_reports: {cleanup_reports.get('total_reports', 0)}",
            f"- mismatches: {cleanup_reports.get('mismatch_reports', 0)}",
            f"- policy_drifts: {cleanup_reports.get('policy_drift_reports', 0)}",
            f"- policy_drift_guidance: {cleanup_reports.get('policy_drift_guidance') or 'n/a'}",
        ]
    )
    if cleanup_reports.get("detail_summary"):
        lines.extend(["- detail_summary:", _indent_block(str(cleanup_reports["detail_summary"]), prefix="  ")])

    lines.extend(
        [
            "",
            "## Related sync audit reports",
            f"- total_reports: {sync_audit_reports.get('total_reports', 0)}",
            f"- mismatches: {sync_audit_reports.get('mismatch_reports', 0)}",
            f"- policy_drifts: {sync_audit_reports.get('policy_drift_reports', 0)}",
            f"- policy_drift_guidance: {sync_audit_reports.get('policy_drift_guidance') or 'n/a'}",
        ]
    )
    if sync_audit_reports.get("detail_summary"):
        lines.extend(
            ["- detail_summary:", _indent_block(str(sync_audit_reports["detail_summary"]), prefix="  ")]
        )

    return "\n".join(lines) + "\n"


def render_sync_health_text(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot, "summary")
    meta = _mapping(snapshot, "meta")
    lines = [
        "Sync health:",
        f"- issue_filter: {meta.get('issue_filter') if meta.get('issue_filter') is not None else 'all'}",
        f"- tracker_filter: {meta.get('tracker_filter') or 'all'}",
        f"- overall_status: {summary.get('overall_status', '-')}",
        f"- pending_artifacts: {summary.get('pending_artifacts', 0)}",
        f"- integrity_issue_count: {summary.get('integrity_issue_count', 0)}",
        f"- repair_changed_reports: {summary.get('repair_changed_reports', 0)}",
        f"- repair_findings_after: {summary.get('repair_findings_after', 0)}",
        f"- cleanup_action_count: {summary.get('cleanup_action_count', 0)}",
        f"- related_report_mismatches: {summary.get('related_report_mismatches', 0)}",
        f"- related_report_policy_drifts: {summary.get('related_report_policy_drifts', 0)}",
    ]
    next_actions = _list_of_strings(summary.get("next_actions"))
    if next_actions:
        lines.append("- next_actions:")
        lines.extend(f"  - {item}" for item in next_actions)
    return "\n".join(lines)


def _serialize_related_report_group(related_reports: dict[str, object]) -> dict[str, object]:
    mismatches = extract_related_report_warning_lines(related_reports.get("mismatches"))
    policy_drifts = extract_related_report_warning_lines(related_reports.get("policy_drifts"))
    guidance = _string_or_none(related_reports.get("policy_drift_guidance"))
    detail_summary = build_related_report_detail_summary(
        mismatch_warnings=mismatches,
        policy_drift_warnings=policy_drifts,
        remediation=guidance if policy_drifts else None,
    )
    return {
        "total_reports": int(related_reports.get("total_reports", 0) or 0),
        "mismatch_reports": int(related_reports.get("mismatch_reports", 0) or 0),
        "policy_drift_reports": int(related_reports.get("policy_drift_reports", 0) or 0),
        "mismatches": list(_list_of_dicts(related_reports.get("mismatches"))),
        "policy_drifts": list(_list_of_dicts(related_reports.get("policy_drifts"))),
        "policy_drift_guidance": guidance,
        "detail_summary": detail_summary,
    }


def _build_sync_health_summary(
    *,
    audit_summary: dict[str, object],
    check_summary: dict[str, object],
    repair_summary: dict[str, object],
    cleanup_summary: dict[str, object],
    related_reports: dict[str, object],
) -> dict[str, object]:
    pending_artifacts = int(audit_summary.get("pending_artifacts", 0) or 0)
    integrity_issue_count = int(audit_summary.get("integrity_issue_count", 0) or 0)
    prunable_groups = int(audit_summary.get("prunable_groups", 0) or 0)
    repair_needed_issues = int(audit_summary.get("repair_needed_issues", 0) or 0)
    check_findings = int(check_summary.get("total_findings", 0) or 0)
    repair_changed_reports = int(repair_summary.get("changed_reports", 0) or 0)
    repair_findings_after = int(repair_summary.get("findings_after", 0) or 0)
    cleanup_action_count = int(cleanup_summary.get("action_count", 0) or 0)
    cleanup_sync_applied_action_count = int(cleanup_summary.get("sync_applied_action_count", 0) or 0)
    cleanup_reports = _mapping(related_reports, "cleanup_reports")
    sync_audit_reports = _mapping(related_reports, "sync_audit_reports")
    related_report_mismatches = int(cleanup_reports.get("mismatch_reports", 0) or 0) + int(
        sync_audit_reports.get("mismatch_reports", 0) or 0
    )
    related_report_policy_drifts = int(cleanup_reports.get("policy_drift_reports", 0) or 0) + int(
        sync_audit_reports.get("policy_drift_reports", 0) or 0
    )

    overall_status = "clean"
    if integrity_issue_count or check_findings or repair_findings_after or repair_needed_issues:
        overall_status = "issues"
    elif (
        pending_artifacts
        or prunable_groups
        or repair_changed_reports
        or cleanup_action_count
        or related_report_mismatches
        or related_report_policy_drifts
    ):
        overall_status = "attention"

    next_actions = _build_next_actions(
        pending_artifacts=pending_artifacts,
        integrity_issue_count=integrity_issue_count,
        repair_changed_reports=repair_changed_reports,
        repair_findings_after=repair_findings_after,
        cleanup_action_count=cleanup_action_count,
        prunable_groups=prunable_groups,
        related_report_mismatches=related_report_mismatches,
        related_report_policy_drifts=related_report_policy_drifts,
    )
    return {
        "overall_status": overall_status,
        "pending_artifacts": pending_artifacts,
        "integrity_issue_count": integrity_issue_count,
        "check_total_findings": check_findings,
        "repair_changed_reports": repair_changed_reports,
        "repair_findings_after": repair_findings_after,
        "cleanup_action_count": cleanup_action_count,
        "cleanup_sync_applied_action_count": cleanup_sync_applied_action_count,
        "prunable_groups": prunable_groups,
        "repair_needed_issues": repair_needed_issues,
        "related_report_mismatches": related_report_mismatches,
        "related_report_policy_drifts": related_report_policy_drifts,
        "next_actions": list(next_actions),
    }


def _build_next_actions(
    *,
    pending_artifacts: int,
    integrity_issue_count: int,
    repair_changed_reports: int,
    repair_findings_after: int,
    cleanup_action_count: int,
    prunable_groups: int,
    related_report_mismatches: int,
    related_report_policy_drifts: int,
) -> tuple[str, ...]:
    actions: list[str] = []
    if pending_artifacts:
        actions.append("Review pending staged artifacts with `republic sync ls` and `republic sync show`.")
    if integrity_issue_count or repair_findings_after:
        actions.append(
            "Inspect applied manifest issues with `republic sync check` and preview repairs with `republic sync repair --dry-run`."
        )
    elif repair_changed_reports:
        actions.append("Apply the reviewed manifest fixes with `republic sync repair`.")
    if cleanup_action_count or prunable_groups:
        actions.append("Review cleanup preview with `republic clean --sync-applied --dry-run --report`.")
    if related_report_mismatches or related_report_policy_drifts:
        actions.append(
            "Refresh raw sync reports with `republic sync audit --format all` and `republic clean --report --report-format all`."
        )
    return tuple(actions)


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list_of_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _render_mapping(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    parts = [f"{key}={value[key]}" for key in sorted(value)]
    return ", ".join(parts)


def _indent_block(value: str, *, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" if line else prefix.rstrip() for line in value.splitlines())
