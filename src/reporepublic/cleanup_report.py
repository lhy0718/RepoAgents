from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reporepublic._related_report_details.rendering import (
    build_related_report_detail_summary,
    extract_related_report_warning_lines,
)
from reporepublic.config import LoadedConfig
from reporepublic.models.domain import utc_now
from reporepublic.report_policy import (
    build_report_freshness_policy_snapshot,
    build_report_policy_drift_guidance,
    build_report_policy_alignment,
)
from reporepublic.utils.files import write_text_file

if TYPE_CHECKING:
    from reporepublic.cli.app import CleanAction


VALID_CLEAN_REPORT_FORMATS = ("json", "markdown")
SYNC_AUDIT_EXPORT = ("sync-audit", "Sync audit", "sync-audit.json", "sync-audit.md")


@dataclass(frozen=True, slots=True)
class CleanupReportBuildResult:
    output_paths: dict[str, Path]
    mode: str
    action_count: int
    related_sync_audit_reports: int
    sync_audit_issue_filter_mismatches: int
    sync_audit_mismatch_warnings: tuple[str, ...]
    sync_audit_policy_drifts: int
    sync_audit_policy_drift_warnings: tuple[str, ...]
    policy_drift_guidance: str | None


def build_cleanup_report(
    loaded: LoadedConfig,
    *,
    actions: list[CleanAction],
    dry_run: bool,
    include_sync_applied: bool,
    issue_id: int | None,
    sync_keep_groups_per_issue: int | None,
    output_path: Path | None = None,
    formats: tuple[str, ...] = ("json",),
) -> CleanupReportBuildResult:
    normalized_formats = normalize_cleanup_report_formats(formats)
    target = output_path or _default_cleanup_report_path(loaded, dry_run=dry_run)
    export_paths = resolve_cleanup_report_export_paths(target, normalized_formats)
    snapshot = build_cleanup_report_snapshot(
        loaded,
        actions=actions,
        dry_run=dry_run,
        include_sync_applied=include_sync_applied,
        issue_id=issue_id,
        sync_keep_groups_per_issue=sync_keep_groups_per_issue,
    )
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_cleanup_report_json(snapshot))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_cleanup_report_markdown(snapshot))
    return CleanupReportBuildResult(
        output_paths=export_paths,
        mode="preview" if dry_run else "applied",
        action_count=len(actions),
        related_sync_audit_reports=int(snapshot["summary"]["related_sync_audit_reports"]),
        sync_audit_issue_filter_mismatches=int(snapshot["summary"]["sync_audit_issue_filter_mismatches"]),
        sync_audit_mismatch_warnings=extract_related_report_warning_lines(
            snapshot["related_reports"].get("mismatches")
        ),
        sync_audit_policy_drifts=int(snapshot["summary"]["sync_audit_policy_drifts"]),
        sync_audit_policy_drift_warnings=extract_related_report_warning_lines(
            snapshot["related_reports"].get("policy_drifts")
        ),
        policy_drift_guidance=_string_or_none(snapshot["related_reports"].get("policy_drift_guidance")),
    )


def build_cleanup_report_snapshot(
    loaded: LoadedConfig,
    *,
    actions: list[CleanAction],
    dry_run: bool,
    include_sync_applied: bool,
    issue_id: int | None,
    sync_keep_groups_per_issue: int | None,
) -> dict[str, object]:
    policy_snapshot = build_report_freshness_policy_snapshot(loaded)
    counts = Counter(action.kind for action in actions)
    affected_issues = sorted({action.issue_id for action in actions if action.issue_id is not None})
    replacement_entry_count = sum(
        len(action.replacement_payload)
        for action in actions
        if isinstance(action.replacement_payload, list)
    )
    related_reports = _load_related_sync_audit_report(
        loaded,
        issue_id=issue_id,
        current_policy=policy_snapshot,
    )
    return {
        "meta": {
            "rendered_at": utc_now().isoformat(),
            "repo_root": str(loaded.repo_root),
            "config_path": str(loaded.config_path),
            "mode": "preview" if dry_run else "applied",
            "issue_filter": issue_id,
            "include_sync_applied": include_sync_applied,
            "sync_keep_groups_per_issue": sync_keep_groups_per_issue,
        },
        "policy": policy_snapshot,
        "summary": {
            "overall_status": "clean" if not actions else ("preview" if dry_run else "cleaned"),
            "action_count": len(actions),
            "affected_issue_count": len(affected_issues),
            "affected_issues": affected_issues,
            "replacement_entry_count": replacement_entry_count,
            "action_counts": dict(sorted(counts.items())),
            "sync_applied_action_count": sum(
                count for kind, count in counts.items() if kind.startswith("sync-applied")
            ),
            "workspace_action_count": counts.get("workspace", 0),
            "artifacts_action_count": counts.get("artifacts", 0),
            "state_action_count": sum(1 for action in actions if action.state_updated),
            "related_sync_audit_reports": related_reports["total_reports"],
            "sync_audit_issue_filter_mismatches": related_reports["mismatch_reports"],
            "sync_audit_policy_drifts": related_reports["policy_drift_reports"],
        },
        "actions": [_serialize_clean_action(action) for action in actions],
        "related_reports": related_reports,
    }


def render_cleanup_report_json(snapshot: dict[str, object]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


def render_cleanup_report_markdown(snapshot: dict[str, object]) -> str:
    meta = _snapshot_mapping(snapshot, "meta")
    policy = _snapshot_mapping(snapshot, "policy")
    summary = _snapshot_mapping(snapshot, "summary")
    actions = _list_of_dicts(snapshot["actions"])
    related_reports = _snapshot_mapping(snapshot, "related_reports")
    lines = [
        "# RepoRepublic Cleanup Report",
        "",
        f"- rendered_at: {meta['rendered_at']}",
        f"- repo_root: {meta['repo_root']}",
        f"- config_path: {meta['config_path']}",
        f"- mode: {meta['mode']}",
        f"- issue_filter: {meta['issue_filter'] if meta['issue_filter'] is not None else 'all'}",
        f"- include_sync_applied: {meta['include_sync_applied']}",
        f"- sync_keep_groups_per_issue: {meta['sync_keep_groups_per_issue'] if meta['sync_keep_groups_per_issue'] is not None else 'n/a'}",
        "",
        "## Policy",
        f"- report_freshness_policy: {policy['summary']}",
        f"- unknown_issues_threshold: {policy['report_freshness_policy']['unknown_issues_threshold']}",
        f"- stale_issues_threshold: {policy['report_freshness_policy']['stale_issues_threshold']}",
        f"- future_attention_threshold: {policy['report_freshness_policy']['future_attention_threshold']}",
        f"- aging_attention_threshold: {policy['report_freshness_policy']['aging_attention_threshold']}",
        "",
        "## Summary",
        f"- overall_status: {summary['overall_status']}",
        f"- action_count: {summary['action_count']}",
        f"- affected_issue_count: {summary['affected_issue_count']}",
        f"- affected_issues: {', '.join(str(value) for value in summary['affected_issues']) if summary['affected_issues'] else 'none'}",
        f"- replacement_entry_count: {summary['replacement_entry_count']}",
        f"- action_counts: {_render_mapping(summary['action_counts'])}",
        f"- sync_applied_action_count: {summary['sync_applied_action_count']}",
        f"- workspace_action_count: {summary['workspace_action_count']}",
        f"- artifacts_action_count: {summary['artifacts_action_count']}",
        f"- state_action_count: {summary['state_action_count']}",
        f"- related_sync_audit_reports: {summary['related_sync_audit_reports']}",
        f"- sync_audit_issue_filter_mismatches: {summary['sync_audit_issue_filter_mismatches']}",
        f"- sync_audit_policy_drifts: {summary['sync_audit_policy_drifts']}",
        "",
        "## Related reports",
        f"- total_reports: {related_reports['total_reports']}",
        f"- mismatch_reports: {related_reports['mismatch_reports']}",
        f"- policy_drift_reports: {related_reports['policy_drift_reports']}",
        f"- policy_drift_guidance: {related_reports['policy_drift_guidance'] or 'n/a'}",
        "",
        "## Actions",
    ]
    related_entries = _list_of_dicts(related_reports["entries"])
    if not related_entries:
        lines.append("- No related sync audit reports found.")
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
        lines.extend(["", "### Sync audit mismatches"])
        for entry in mismatches:
            lines.append(
                f"- {entry['label']}: {entry['warning'] or 'issue filter mismatch'}"
            )
    policy_drifts = _list_of_dicts(related_reports["policy_drifts"])
    if policy_drifts:
        lines.extend(["", "### Sync audit policy drifts"])
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
    if not actions:
        lines.append("- No cleanup actions were generated.")
        return "\n".join(lines) + "\n"
    for action in actions:
        lines.extend(
            [
                "",
                f"### {action['kind']}",
                f"- path: {action['path']}",
                f"- issue_id: {action['issue_id'] if action['issue_id'] is not None else 'n/a'}",
                f"- run_id: {action['run_id'] or 'n/a'}",
                f"- detail: {action['detail'] or 'n/a'}",
                f"- state_updated: {action['state_updated']}",
                f"- replacement_entry_count: {action['replacement_entry_count']}",
            ]
        )
    return "\n".join(lines) + "\n"


def normalize_cleanup_report_formats(formats: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if not formats:
        return ("json",)
    normalized: list[str] = []
    for value in formats:
        lowered = value.strip().lower()
        if not lowered:
            continue
        if lowered == "all":
            for item in VALID_CLEAN_REPORT_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_CLEAN_REPORT_FORMATS:
            valid = ", ".join((*VALID_CLEAN_REPORT_FORMATS, "all"))
            raise ValueError(f"Unsupported cleanup report format '{value}'. Expected one of: {valid}")
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def resolve_cleanup_report_export_paths(base_output: Path, formats: tuple[str, ...]) -> dict[str, Path]:
    target = base_output
    if target.exists() and target.is_dir():
        target = target / "cleanup-report.json"
    elif target.suffix.lower() not in {".json", ".md"}:
        target = target.with_suffix(".json")
    suffix_map = {
        "json": ".json",
        "markdown": ".md",
    }
    return {
        export_format: target.with_suffix(suffix_map[export_format]) for export_format in formats
    }


def _default_cleanup_report_path(loaded: LoadedConfig, *, dry_run: bool) -> Path:
    filename = "cleanup-preview.json" if dry_run else "cleanup-result.json"
    return loaded.reports_dir / filename


def _load_related_sync_audit_report(
    loaded: LoadedConfig,
    *,
    issue_id: int | None,
    current_policy: dict[str, object],
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    mismatches: list[dict[str, object]] = []
    policy_drifts: list[dict[str, object]] = []
    remediation = build_report_policy_drift_guidance()["detail"]
    key, label, json_name, markdown_name = SYNC_AUDIT_EXPORT
    json_path = loaded.reports_dir / json_name
    markdown_path = loaded.reports_dir / markdown_name
    if not json_path.exists() and not markdown_path.exists():
        return {
            "total_reports": 0,
            "entries": [],
            "mismatch_reports": 0,
            "mismatches": [],
            "policy_drift_reports": 0,
            "policy_drift_guidance": None,
            "policy_drifts": [],
            "detail_summary": None,
        }
    payload = _load_report_payload(json_path) if json_path.exists() else None
    entry = _serialize_related_sync_audit_report(
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
            f"sync audit issue_filter={entry_issue_filter} does not match cleanup issue_filter={issue_id}"
        )
        mismatches.append(entry)
    else:
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


def _serialize_related_sync_audit_report(
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
    summary = "Sync audit export available."
    metrics: dict[str, object] = {}
    if payload is None and json_path is not None:
        status = "invalid"
        summary = "Sync audit JSON could not be parsed."
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
            pending_artifacts = report_summary.get("pending_artifacts", 0)
            integrity_issue_count = report_summary.get("integrity_issue_count", 0)
            prunable_groups = report_summary.get("prunable_groups", 0)
            summary = (
                f"pending={pending_artifacts} "
                f"integrity_issues={integrity_issue_count} "
                f"prunable_groups={prunable_groups}"
            )
            metrics = {
                "pending_artifacts": pending_artifacts,
                "integrity_issue_count": integrity_issue_count,
                "prunable_groups": prunable_groups,
                "repair_needed_issues": report_summary.get("repair_needed_issues", 0),
                "cleanup_report_mismatches": report_summary.get("cleanup_report_mismatches", 0),
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


def _serialize_clean_action(action: CleanAction) -> dict[str, object]:
    replacement_entry_count = len(action.replacement_payload) if isinstance(action.replacement_payload, list) else 0
    return {
        "kind": action.kind,
        "path": str(action.path),
        "issue_id": action.issue_id,
        "run_id": action.run_id,
        "state_updated": action.state_updated,
        "detail": action.detail,
        "replacement_entry_count": replacement_entry_count,
    }


def _render_mapping(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    return ", ".join(f"{key}={item}" for key, item in sorted(value.items()))


def _snapshot_mapping(snapshot: dict[str, object], key: str) -> dict[str, object]:
    value = snapshot[key]
    if not isinstance(value, dict):
        raise TypeError(f"Cleanup report snapshot field '{key}' must be a mapping.")
    return value


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
