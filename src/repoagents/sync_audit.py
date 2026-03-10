from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from repoagents._related_report_details.rendering import (
    build_related_report_detail_summary,
    extract_related_report_warning_lines,
)
from repoagents.config import LoadedConfig
from repoagents.models.domain import utc_now
from repoagents.report_policy import (
    build_report_freshness_policy_snapshot,
    build_report_policy_drift_guidance,
    build_report_policy_alignment,
)
from repoagents.sync_manifest_reports import (
    serialize_sync_manifest_finding,
    serialize_sync_manifest_report,
)
from repoagents.sync_artifacts import (
    AppliedSyncManifestFinding,
    AppliedSyncManifestReport,
    SyncAppliedRetentionGroup,
    SyncAppliedRetentionIssueSummary,
    SyncAppliedRetentionSnapshot,
    SyncArtifact,
    inspect_applied_sync_manifests,
    list_sync_artifacts,
    summarize_sync_applied_retention,
)
from repoagents.utils.files import write_text_file


VALID_SYNC_AUDIT_FORMATS = ("json", "markdown")
CLEANUP_REPORT_EXPORTS = (
    ("cleanup-preview", "Cleanup preview", "cleanup-preview.json", "cleanup-preview.md"),
    ("cleanup-result", "Cleanup result", "cleanup-result.json", "cleanup-result.md"),
)


@dataclass(frozen=True, slots=True)
class SyncAuditBuildResult:
    output_paths: dict[str, Path]
    overall_status: str
    pending_artifacts: int
    integrity_issue_count: int
    prunable_groups: int
    related_cleanup_reports: int
    cleanup_report_mismatches: int
    cleanup_mismatch_warnings: tuple[str, ...]
    related_cleanup_policy_drifts: int
    cleanup_policy_drift_warnings: tuple[str, ...]
    policy_drift_guidance: str | None


def build_sync_audit_report(
    loaded: LoadedConfig,
    *,
    output_path: Path | None = None,
    formats: tuple[str, ...] = ("json", "markdown"),
    issue_id: int | None = None,
    tracker: str | None = None,
    limit: int = 50,
) -> SyncAuditBuildResult:
    normalized_formats = normalize_sync_audit_formats(formats)
    target = output_path or (loaded.reports_dir / "sync-audit.json")
    export_paths = resolve_sync_audit_export_paths(target, normalized_formats)
    snapshot = build_sync_audit_snapshot(
        loaded,
        issue_id=issue_id,
        tracker=tracker,
        limit=limit,
    )
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_sync_audit_json(snapshot))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_sync_audit_markdown(snapshot))
    summary = _snapshot_mapping(snapshot, "summary")
    return SyncAuditBuildResult(
        output_paths=export_paths,
        overall_status=str(summary["overall_status"]),
        pending_artifacts=int(summary["pending_artifacts"]),
        integrity_issue_count=int(summary["integrity_issue_count"]),
        prunable_groups=int(summary["prunable_groups"]),
        related_cleanup_reports=int(summary["related_cleanup_reports"]),
        cleanup_report_mismatches=int(summary["cleanup_report_mismatches"]),
        cleanup_mismatch_warnings=extract_related_report_warning_lines(
            snapshot["related_reports"].get("mismatches")
        ),
        related_cleanup_policy_drifts=int(summary["related_cleanup_policy_drifts"]),
        cleanup_policy_drift_warnings=extract_related_report_warning_lines(
            snapshot["related_reports"].get("policy_drifts")
        ),
        policy_drift_guidance=_string_or_none(snapshot["related_reports"].get("policy_drift_guidance")),
    )


def build_sync_audit_snapshot(
    loaded: LoadedConfig,
    *,
    issue_id: int | None = None,
    tracker: str | None = None,
    limit: int = 50,
) -> dict[str, object]:
    policy_snapshot = build_report_freshness_policy_snapshot(loaded)
    pending_artifacts = list_sync_artifacts(
        loaded,
        issue_id=issue_id,
        tracker=tracker,
        scope="pending",
    )
    integrity_reports = inspect_applied_sync_manifests(
        loaded,
        issue_id=issue_id,
        tracker=tracker,
    )
    retention = summarize_sync_applied_retention(
        loaded,
        issue_id=issue_id,
        tracker=tracker,
        limit=limit,
    )
    related_reports = _load_related_cleanup_reports(
        loaded,
        issue_id=issue_id,
        current_policy=policy_snapshot,
    )
    pending_issue_count = len({artifact.issue_id for artifact in pending_artifacts if artifact.issue_id is not None})
    integrity_issue_count = sum(1 for report in integrity_reports if report.findings)
    overall_status = _sync_audit_status(
        pending_artifacts=len(pending_artifacts),
        integrity_issue_count=integrity_issue_count,
        prunable_groups=retention.prunable_groups,
    )
    return {
        "meta": {
            "rendered_at": utc_now().isoformat(),
            "repo_root": str(loaded.repo_root),
            "config_path": str(loaded.config_path),
            "issue_filter": issue_id,
            "tracker_filter": tracker,
            "limit": limit,
        },
        "policy": policy_snapshot,
        "summary": {
            "overall_status": overall_status,
            "pending_artifacts": len(pending_artifacts),
            "pending_issues": pending_issue_count,
            "integrity_issue_count": integrity_issue_count,
            "applied_issue_reports": len(integrity_reports),
            "prunable_issues": retention.prunable_issues,
            "prunable_groups": retention.prunable_groups,
            "prunable_bytes": retention.prunable_bytes,
            "prunable_bytes_human": _format_bytes(retention.prunable_bytes),
            "repair_needed_issues": retention.repair_needed_issues,
            "related_cleanup_reports": related_reports["total_reports"],
            "cleanup_report_mismatches": related_reports["mismatch_reports"],
            "related_cleanup_policy_drifts": related_reports["policy_drift_reports"],
        },
        "pending": _serialize_pending_inventory(pending_artifacts, limit=limit),
        "integrity": _serialize_integrity_reports(integrity_reports),
        "retention": _serialize_retention_snapshot(retention),
        "related_reports": related_reports,
    }


def render_sync_audit_json(snapshot: dict[str, object]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


def render_sync_audit_markdown(snapshot: dict[str, object]) -> str:
    meta = _snapshot_mapping(snapshot, "meta")
    policy = _snapshot_mapping(snapshot, "policy")
    summary = _snapshot_mapping(snapshot, "summary")
    pending = _snapshot_mapping(snapshot, "pending")
    integrity = _snapshot_mapping(snapshot, "integrity")
    retention = _snapshot_mapping(snapshot, "retention")
    related_reports = _snapshot_mapping(snapshot, "related_reports")

    lines = [
        "# RepoAgents Sync Audit",
        "",
        f"- rendered_at: {meta['rendered_at']}",
        f"- repo_root: {meta['repo_root']}",
        f"- config_path: {meta['config_path']}",
        f"- issue_filter: {meta['issue_filter'] if meta['issue_filter'] is not None else 'all'}",
        f"- tracker_filter: {meta['tracker_filter'] or 'all'}",
        f"- overall_status: {summary['overall_status']}",
        "",
        "## Policy",
        f"- report_freshness_policy: {policy['summary']}",
        f"- unknown_issues_threshold: {policy['report_freshness_policy']['unknown_issues_threshold']}",
        f"- stale_issues_threshold: {policy['report_freshness_policy']['stale_issues_threshold']}",
        f"- future_attention_threshold: {policy['report_freshness_policy']['future_attention_threshold']}",
        f"- aging_attention_threshold: {policy['report_freshness_policy']['aging_attention_threshold']}",
        "",
        "## Summary",
        f"- pending_artifacts: {summary['pending_artifacts']}",
        f"- pending_issues: {summary['pending_issues']}",
        f"- integrity_issue_count: {summary['integrity_issue_count']}",
        f"- applied_issue_reports: {summary['applied_issue_reports']}",
        f"- prunable_issues: {summary['prunable_issues']}",
        f"- prunable_groups: {summary['prunable_groups']}",
        f"- prunable_bytes: {summary['prunable_bytes_human']}",
        f"- repair_needed_issues: {summary['repair_needed_issues']}",
        f"- related_cleanup_reports: {summary['related_cleanup_reports']}",
        f"- cleanup_report_mismatches: {summary['cleanup_report_mismatches']}",
        f"- related_cleanup_policy_drifts: {summary['related_cleanup_policy_drifts']}",
        "",
        "## Pending staged artifacts",
        f"- total: {pending['total_artifacts']}",
        f"- issue_count: {pending['issue_count']}",
        f"- tracker_counts: {_render_mapping(pending['tracker_counts'])}",
        f"- action_counts: {_render_mapping(pending['action_counts'])}",
    ]
    pending_entries = _list_of_dicts(pending["entries"])
    if not pending_entries:
        lines.append("- No pending sync artifacts.")
    else:
        for entry in pending_entries:
            issue_label = entry["issue_id"] if entry["issue_id"] is not None else "unknown"
            lines.extend(
                [
                    "",
                    f"### Pending {entry['action']} · issue #{issue_label}",
                    f"- tracker: {entry['tracker']}",
                    f"- staged_at: {entry['staged_at'] or 'n/a'}",
                    f"- relative_path: {entry['relative_path']}",
                    f"- artifact_role: {entry['artifact_role'] or 'n/a'}",
                    f"- summary: {entry['summary'] or 'n/a'}",
                ]
            )

    lines.extend(
        [
            "",
            "## Applied manifest integrity",
            f"- total_reports: {integrity['total_reports']}",
            f"- issues_with_findings: {integrity['issues_with_findings']}",
            f"- clean_issues: {integrity['clean_issues']}",
            f"- finding_counts: {_render_mapping(integrity['finding_counts'])}",
        ]
    )
    reports = _list_of_dicts(integrity["reports"])
    if not reports:
        lines.append("- No applied sync manifests found.")
    else:
        for report in reports:
            issue_label = report["issue_id"] if report["issue_id"] is not None else "unknown"
            lines.extend(
                [
                    "",
                    f"### Integrity {report['tracker']} · issue #{issue_label}",
                    f"- status: {report['status']}",
                    f"- manifest_path: {report['manifest_path']}",
                    f"- manifest_exists: {report['manifest_exists']}",
                    f"- entries: {report['manifest_entry_count']}",
                    f"- archives: {report['archive_file_count']}",
                    f"- findings: {report['finding_count']}",
                ]
            )
            findings = _list_of_dicts(report["findings"])
            if findings:
                lines.append("- finding_details:")
                for finding in findings:
                    lines.append(
                        "  - "
                        f"{finding['code']} path={finding['path'] or '-'} entry_key={finding['entry_key'] or '-'} {finding['message']}"
                    )

    lines.extend(
        [
            "",
            "## Applied retention",
            f"- keep_groups_per_issue: {retention['keep_groups_per_issue']}",
            f"- total_issues: {retention['total_issues']}",
            f"- eligible_issues: {retention['eligible_issues']}",
            f"- stable_issues: {retention['stable_issues']}",
            f"- prunable_issues: {retention['prunable_issues']}",
            f"- repair_needed_issues: {retention['repair_needed_issues']}",
            f"- total_groups: {retention['total_groups']}",
            f"- kept_groups: {retention['kept_groups']}",
            f"- prunable_groups: {retention['prunable_groups']}",
            f"- total_bytes: {retention['total_bytes_human']}",
            f"- kept_bytes: {retention['kept_bytes_human']}",
            f"- prunable_bytes: {retention['prunable_bytes_human']}",
        ]
    )
    retention_entries = _list_of_dicts(retention["entries"])
    if not retention_entries:
        lines.append("- No applied retention entries.")
    else:
        for entry in retention_entries:
            issue_label = entry["issue_id"] if entry["issue_id"] is not None else "unknown"
            lines.extend(
                [
                    "",
                    f"### Retention {entry['tracker']} · issue #{issue_label}",
                    f"- status: {entry['status']}",
                    f"- integrity_findings: {entry['integrity_findings']}",
                    f"- finding_codes: {', '.join(str(code) for code in entry['finding_codes']) if entry['finding_codes'] else 'none'}",
                    f"- groups: total={entry['total_groups']} kept={entry['kept_groups']} prunable={entry['prunable_groups']}",
                    f"- bytes: total={entry['total_bytes_human']} kept={entry['kept_bytes_human']} prunable={entry['prunable_bytes_human']}",
                    f"- ages: newest={entry['newest_group_age_human']} oldest={entry['oldest_group_age_human']} oldest_prunable={entry['oldest_prunable_group_age_human']}",
                ]
            )
            groups = _list_of_dicts(entry["groups"])
            if groups:
                lines.append("- groups:")
                for group in groups:
                    lines.append(
                        "  - "
                        f"{group['status']} key={group['group_key']} actions={','.join(group['actions']) or 'none'} "
                        f"size={group['total_bytes_human']} newest={group['newest_age_human']}"
                    )
    lines.extend(
        [
            "",
            "## Related cleanup reports",
            f"- total_reports: {related_reports['total_reports']}",
            f"- mismatch_reports: {related_reports['mismatch_reports']}",
            f"- policy_drift_reports: {related_reports['policy_drift_reports']}",
            f"- policy_drift_guidance: {related_reports['policy_drift_guidance'] or 'n/a'}",
        ]
    )
    related_entries = _list_of_dicts(related_reports["entries"])
    if not related_entries:
        lines.append("- No related cleanup reports found.")
    else:
        for entry in related_entries:
            lines.extend(
                [
                    "",
                    f"### {entry['label']}",
                    f"- status: {entry['status']}",
                    f"- generated_at: {entry['generated_at'] or 'n/a'}",
                    f"- issue_filter: {entry['issue_filter'] if entry['issue_filter'] is not None else 'all'}",
                    f"- summary: {entry['summary']}",
                    f"- json_path: {entry['json_path'] or 'n/a'}",
                    f"- markdown_path: {entry['markdown_path'] or 'n/a'}",
                    f"- metrics: {_render_mapping(entry['metrics'])}",
                    f"- policy_alignment: {entry['policy_alignment']['status']}",
                    f"- embedded_policy: {entry['policy_alignment']['embedded_summary'] or 'n/a'}",
                    f"- policy_warning: {entry['policy_alignment']['warning']}",
                    f"- policy_remediation: {entry['policy_alignment']['remediation'] or 'n/a'}",
                ]
            )
    mismatches = _list_of_dicts(related_reports["mismatches"])
    if mismatches:
        lines.extend(["", "### Cleanup report mismatches"])
        for entry in mismatches:
            lines.append(
                f"- {entry['label']}: {entry['warning'] or 'issue filter mismatch'}"
            )
    policy_drifts = _list_of_dicts(related_reports["policy_drifts"])
    if policy_drifts:
        lines.extend(["", "### Cleanup report policy drifts"])
        for entry in policy_drifts:
            lines.extend(
                [
                    "",
                    f"#### {entry['label']}",
                    f"- warning: {entry['warning']}",
                    f"- embedded_policy: {entry['embedded_summary'] or 'n/a'}",
                    f"- current_policy: {entry['current_summary'] or 'n/a'}",
                    f"- remediation: {entry['remediation'] or 'n/a'}",
                ]
            )
    return "\n".join(lines) + "\n"


def normalize_sync_audit_formats(formats: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if not formats:
        return ("json", "markdown")
    normalized: list[str] = []
    for value in formats:
        lowered = value.strip().lower()
        if not lowered:
            continue
        if lowered == "all":
            for item in VALID_SYNC_AUDIT_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_SYNC_AUDIT_FORMATS:
            valid = ", ".join((*VALID_SYNC_AUDIT_FORMATS, "all"))
            raise ValueError(f"Unsupported sync audit format '{value}'. Expected one of: {valid}")
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json", "markdown"))


def resolve_sync_audit_export_paths(base_output: Path, formats: tuple[str, ...]) -> dict[str, Path]:
    target = base_output
    if target.exists() and target.is_dir():
        target = target / "sync-audit.json"
    elif target.suffix.lower() not in {".json", ".md"}:
        target = target.with_suffix(".json")
    suffix_map = {
        "json": ".json",
        "markdown": ".md",
    }
    return {
        export_format: target.with_suffix(suffix_map[export_format]) for export_format in formats
    }


def _serialize_pending_inventory(artifacts: list[SyncArtifact], *, limit: int) -> dict[str, object]:
    ordered = sorted(
        artifacts,
        key=lambda artifact: (
            str(artifact.staged_at or ""),
            artifact.relative_path,
        ),
        reverse=True,
    )
    tracker_counts = Counter(artifact.tracker for artifact in artifacts)
    action_counts = Counter(artifact.action for artifact in artifacts)
    return {
        "total_artifacts": len(artifacts),
        "issue_count": len({artifact.issue_id for artifact in artifacts if artifact.issue_id is not None}),
        "tracker_counts": dict(sorted(tracker_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "entries": [_serialize_pending_artifact(artifact) for artifact in ordered[:limit]],
    }


def _serialize_pending_artifact(artifact: SyncArtifact) -> dict[str, object]:
    return {
        "tracker": artifact.tracker,
        "issue_id": artifact.issue_id,
        "action": artifact.action,
        "staged_at": artifact.staged_at,
        "relative_path": artifact.relative_path,
        "summary": artifact.summary,
        "artifact_role": artifact.normalized.get("artifact_role"),
        "issue_key": artifact.normalized.get("issue_key"),
        "bundle_key": artifact.normalized.get("bundle_key"),
    }


def _serialize_integrity_reports(reports: list[AppliedSyncManifestReport]) -> dict[str, object]:
    finding_counts = Counter(
        finding.code
        for report in reports
        for finding in report.findings
    )
    return {
        "total_reports": len(reports),
        "issues_with_findings": sum(1 for report in reports if report.findings),
        "clean_issues": sum(1 for report in reports if not report.findings),
        "finding_counts": dict(sorted(finding_counts.items())),
        "reports": [_serialize_integrity_report(report) for report in reports],
    }


def _serialize_integrity_report(report: AppliedSyncManifestReport) -> dict[str, object]:
    return serialize_sync_manifest_report(report)


def _serialize_integrity_finding(finding: AppliedSyncManifestFinding) -> dict[str, object]:
    return serialize_sync_manifest_finding(finding)


def _serialize_retention_snapshot(snapshot: SyncAppliedRetentionSnapshot) -> dict[str, object]:
    return {
        "keep_groups_per_issue": snapshot.keep_groups_per_issue,
        "total_issues": snapshot.total_issues,
        "eligible_issues": snapshot.eligible_issues,
        "stable_issues": snapshot.stable_issues,
        "prunable_issues": snapshot.prunable_issues,
        "repair_needed_issues": snapshot.repair_needed_issues,
        "total_groups": snapshot.total_groups,
        "kept_groups": snapshot.kept_groups,
        "prunable_groups": snapshot.prunable_groups,
        "total_bytes": snapshot.total_bytes,
        "kept_bytes": snapshot.kept_bytes,
        "prunable_bytes": snapshot.prunable_bytes,
        "total_bytes_human": _format_bytes(snapshot.total_bytes),
        "kept_bytes_human": _format_bytes(snapshot.kept_bytes),
        "prunable_bytes_human": _format_bytes(snapshot.prunable_bytes),
        "entries": [_serialize_retention_issue(entry) for entry in snapshot.entries],
    }


def _serialize_retention_issue(entry: SyncAppliedRetentionIssueSummary) -> dict[str, object]:
    return {
        "tracker": entry.tracker,
        "issue_id": entry.issue_id,
        "status": entry.status,
        "keep_groups_limit": entry.keep_groups_limit,
        "integrity_findings": entry.integrity_findings,
        "finding_codes": list(entry.finding_codes),
        "issue_root_path": str(entry.issue_root),
        "manifest_path": str(entry.manifest_path),
        "total_groups": entry.total_groups,
        "kept_groups": entry.kept_groups,
        "prunable_groups": entry.prunable_groups,
        "total_bytes": entry.total_bytes,
        "kept_bytes": entry.kept_bytes,
        "prunable_bytes": entry.prunable_bytes,
        "total_bytes_human": _format_bytes(entry.total_bytes),
        "kept_bytes_human": _format_bytes(entry.kept_bytes),
        "prunable_bytes_human": _format_bytes(entry.prunable_bytes),
        "newest_group_age_seconds": entry.newest_group_age_seconds,
        "oldest_group_age_seconds": entry.oldest_group_age_seconds,
        "oldest_prunable_group_age_seconds": entry.oldest_prunable_group_age_seconds,
        "newest_group_age_human": _format_age_seconds(entry.newest_group_age_seconds),
        "oldest_group_age_human": _format_age_seconds(entry.oldest_group_age_seconds),
        "oldest_prunable_group_age_human": _format_age_seconds(entry.oldest_prunable_group_age_seconds),
        "groups": [_serialize_retention_group(group) for group in entry.groups],
    }


def _serialize_retention_group(group: SyncAppliedRetentionGroup) -> dict[str, object]:
    return {
        "group_key": group.group_key,
        "status": group.status,
        "actions": list(group.actions),
        "archive_paths": list(group.archive_paths),
        "archive_file_count": group.archive_file_count,
        "total_bytes": group.total_bytes,
        "total_bytes_human": _format_bytes(group.total_bytes),
        "newest_at": group.newest_at,
        "oldest_at": group.oldest_at,
        "newest_age_seconds": group.newest_age_seconds,
        "oldest_age_seconds": group.oldest_age_seconds,
        "newest_age_human": _format_age_seconds(group.newest_age_seconds),
        "oldest_age_human": _format_age_seconds(group.oldest_age_seconds),
    }


def _load_related_cleanup_reports(
    loaded: LoadedConfig,
    *,
    issue_id: int | None,
    current_policy: dict[str, object],
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    mismatches: list[dict[str, object]] = []
    policy_drifts: list[dict[str, object]] = []
    remediation = build_report_policy_drift_guidance()["detail"]
    for key, label, json_name, markdown_name in CLEANUP_REPORT_EXPORTS:
        json_path = loaded.reports_dir / json_name
        markdown_path = loaded.reports_dir / markdown_name
        if not json_path.exists() and not markdown_path.exists():
            continue
        payload = _load_report_payload(json_path) if json_path.exists() else None
        entry = _serialize_related_cleanup_report(
            key=key,
            label=label,
            json_path=json_path if json_path.exists() else None,
            markdown_path=markdown_path if markdown_path.exists() else None,
            payload=payload,
            current_policy=current_policy,
        )
        entry_issue_filter = entry["issue_filter"]
        if issue_id is not None and entry_issue_filter not in (None, issue_id):
            entry["match_status"] = "mismatch"
            entry["warning"] = (
                f"cleanup report issue_filter={entry_issue_filter} does not match audit issue_filter={issue_id}"
            )
            mismatches.append(entry)
            continue
        entry["match_status"] = "global" if entry_issue_filter is None else "match"
        entry["warning"] = None
        entries.append(entry)
        alignment = entry.get("policy_alignment")
        if isinstance(alignment, dict) and alignment.get("status") == "drift":
            policy_drifts.append(
                {
                    "key": entry["key"],
                    "label": entry["label"],
                    "warning": alignment.get("warning"),
                    "remediation": alignment.get("remediation"),
                    "embedded_summary": alignment.get("embedded_summary"),
                    "current_summary": alignment.get("current_summary"),
                }
            )
    return {
        "total_reports": len(entries),
        "entries": entries,
        "mismatch_reports": len(mismatches),
        "mismatches": mismatches,
        "policy_drift_reports": len(policy_drifts),
        "policy_drift_guidance": remediation if policy_drifts else None,
        "policy_drifts": policy_drifts,
        "detail_summary": build_related_report_detail_summary(
            mismatch_warnings=extract_related_report_warning_lines(mismatches),
            policy_drift_warnings=extract_related_report_warning_lines(policy_drifts),
            remediation=remediation if policy_drifts else None,
        ),
    }


def _load_report_payload(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _serialize_related_cleanup_report(
    *,
    key: str,
    label: str,
    json_path: Path | None,
    markdown_path: Path | None,
    payload: dict[str, object] | None,
    current_policy: dict[str, object],
) -> dict[str, object]:
    status = "available"
    generated_at: str | None = None
    issue_filter: int | None = None
    summary = "Cleanup report export available."
    metrics: dict[str, object] = {}
    if payload is None and json_path is not None:
        status = "invalid"
        summary = "Cleanup report JSON could not be parsed."
    elif payload is not None:
        meta = payload.get("meta")
        if isinstance(meta, dict):
            generated_at = _string_or_none(meta.get("rendered_at"))
            raw_issue_filter = meta.get("issue_filter")
            if isinstance(raw_issue_filter, int):
                issue_filter = raw_issue_filter
        report_summary = payload.get("summary")
        if isinstance(report_summary, dict):
            status = _string_or_none(report_summary.get("overall_status")) or status
            action_count = report_summary.get("action_count", 0)
            affected_issue_count = report_summary.get("affected_issue_count", 0)
            summary = f"actions={action_count} affected_issues={affected_issue_count}"
            metrics = {
                "action_count": action_count,
                "affected_issue_count": affected_issue_count,
                "sync_applied_action_count": report_summary.get("sync_applied_action_count", 0),
                "replacement_entry_count": report_summary.get("replacement_entry_count", 0),
            }
    return {
        "key": key,
        "label": label,
        "status": status,
        "generated_at": generated_at,
        "issue_filter": issue_filter,
        "summary": summary,
        "metrics": metrics,
        "policy_alignment": build_report_policy_alignment(
            current_policy=current_policy,
            payload=payload,
        ),
        "match_status": "unknown",
        "warning": None,
        "json_path": str(json_path) if json_path else None,
        "markdown_path": str(markdown_path) if markdown_path else None,
    }


def _sync_audit_status(*, pending_artifacts: int, integrity_issue_count: int, prunable_groups: int) -> str:
    if integrity_issue_count > 0:
        return "issues"
    if prunable_groups > 0 or pending_artifacts > 0:
        return "attention"
    return "ok"


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    size = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(value)} B"


def _format_age_seconds(value: int | None) -> str:
    if value is None:
        return "n/a"
    remaining = int(value)
    days, remainder = divmod(remaining, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _render_mapping(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    return ", ".join(f"{key}={item}" for key, item in sorted(value.items()))


def _snapshot_mapping(snapshot: dict[str, object], key: str) -> dict[str, object]:
    value = snapshot[key]
    if not isinstance(value, dict):
        raise TypeError(f"Sync audit snapshot field '{key}' must be a mapping.")
    return value


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
