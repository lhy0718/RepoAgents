from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from reporepublic.config import LoadedConfig
from reporepublic.models.domain import utc_now
from reporepublic.sync_artifacts import (
    AppliedSyncManifestFinding,
    AppliedSyncManifestRepairResult,
    AppliedSyncManifestReport,
    inspect_applied_sync_manifests,
    repair_applied_sync_manifests,
)
from reporepublic.utils.files import write_text_file


VALID_SYNC_MANIFEST_REPORT_FORMATS = ("json", "markdown")


@dataclass(frozen=True, slots=True)
class SyncCheckReportBuildResult:
    output_paths: dict[str, Path]
    overall_status: str
    total_reports: int
    issues_with_findings: int
    total_findings: int


@dataclass(frozen=True, slots=True)
class SyncRepairReportBuildResult:
    output_paths: dict[str, Path]
    overall_status: str
    total_reports: int
    changed_reports: int
    findings_before: int
    findings_after: int
    dropped_entries: int
    adopted_archives: int
    normalized_entries: int


def normalize_sync_manifest_report_formats(
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
            for item in VALID_SYNC_MANIFEST_REPORT_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_SYNC_MANIFEST_REPORT_FORMATS:
            raise ValueError(
                "Unsupported sync manifest report format. Expected one of: json, markdown, all"
            )
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def resolve_sync_manifest_report_export_paths(
    target: Path,
    formats: tuple[str, ...],
) -> dict[str, Path]:
    export_paths: dict[str, Path] = {}
    resolved = target.resolve()
    for export_format in formats:
        suffix = ".md" if export_format == "markdown" else ".json"
        export_paths[export_format] = resolved.with_suffix(suffix)
    return export_paths


def build_sync_check_report(
    loaded: LoadedConfig,
    *,
    output_path: Path | None = None,
    formats: tuple[str, ...] = ("json",),
    issue_id: int | None = None,
    tracker: str | None = None,
) -> SyncCheckReportBuildResult:
    normalized_formats = normalize_sync_manifest_report_formats(formats)
    target = output_path or (loaded.reports_dir / "sync-check.json")
    export_paths = resolve_sync_manifest_report_export_paths(target, normalized_formats)
    snapshot = build_sync_check_snapshot(
        loaded,
        issue_id=issue_id,
        tracker=tracker,
    )
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_sync_check_json(snapshot))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_sync_check_markdown(snapshot))
    summary = _mapping(snapshot, "summary")
    return SyncCheckReportBuildResult(
        output_paths=export_paths,
        overall_status=str(summary.get("overall_status", "clean")),
        total_reports=int(summary.get("total_reports", 0)),
        issues_with_findings=int(summary.get("issues_with_findings", 0)),
        total_findings=int(summary.get("total_findings", 0)),
    )


def build_sync_check_snapshot(
    loaded: LoadedConfig,
    *,
    issue_id: int | None = None,
    tracker: str | None = None,
) -> dict[str, object]:
    reports = inspect_applied_sync_manifests(loaded, issue_id=issue_id, tracker=tracker)
    finding_counts = Counter(
        finding.code
        for report in reports
        for finding in report.findings
    )
    issues_with_findings = sum(1 for report in reports if report.findings)
    total_findings = sum(len(report.findings) for report in reports)
    return {
        "meta": {
            "rendered_at": utc_now().isoformat(),
            "repo_root": str(loaded.repo_root),
            "config_path": str(loaded.config_path),
            "issue_filter": issue_id,
            "tracker_filter": tracker,
        },
        "summary": {
            "overall_status": "issues" if issues_with_findings else "clean",
            "total_reports": len(reports),
            "issues_with_findings": issues_with_findings,
            "clean_reports": sum(1 for report in reports if not report.findings),
            "total_findings": total_findings,
            "finding_counts": dict(sorted(finding_counts.items())),
        },
        "reports": [
            serialize_sync_manifest_report(report, include_issue_root=True)
            for report in reports
        ],
    }


def render_sync_check_json(snapshot: dict[str, object]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


def render_sync_check_markdown(snapshot: dict[str, object]) -> str:
    meta = _mapping(snapshot, "meta")
    summary = _mapping(snapshot, "summary")
    reports = _list_of_dicts(snapshot.get("reports"))
    lines = [
        "# RepoRepublic Sync Check",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- config_path: {meta.get('config_path', '-')}",
        f"- issue_filter: {meta.get('issue_filter') if meta.get('issue_filter') is not None else 'all'}",
        f"- tracker_filter: {meta.get('tracker_filter') or 'all'}",
        "",
        "## Summary",
        f"- overall_status: {summary.get('overall_status', '-')}",
        f"- total_reports: {summary.get('total_reports', 0)}",
        f"- issues_with_findings: {summary.get('issues_with_findings', 0)}",
        f"- clean_reports: {summary.get('clean_reports', 0)}",
        f"- total_findings: {summary.get('total_findings', 0)}",
        f"- finding_counts: {_render_mapping(summary.get('finding_counts'))}",
        "",
        "## Reports",
    ]
    if not reports:
        lines.append("- No applied sync manifests found.")
        return "\n".join(lines) + "\n"
    for report in reports:
        issue_label = report.get("issue_id")
        lines.extend(
            [
                "",
                f"### {report.get('tracker', '-')} · issue #{issue_label if issue_label is not None else 'unknown'}",
                f"- status: {report.get('status', '-')}",
                f"- issue_root: {report.get('issue_root', '-')}",
                f"- manifest_path: {report.get('manifest_path', '-')}",
                f"- manifest_exists: {report.get('manifest_exists', False)}",
                f"- manifest_entry_count: {report.get('manifest_entry_count', 0)}",
                f"- archive_file_count: {report.get('archive_file_count', 0)}",
                f"- finding_count: {report.get('finding_count', 0)}",
            ]
        )
        findings = _list_of_dicts(report.get("findings"))
        if findings:
            lines.append("- finding_details:")
            for finding in findings:
                lines.append(
                    "  - "
                    f"{finding.get('code', '-')} path={finding.get('path') or '-'} "
                    f"entry_key={finding.get('entry_key') or '-'} {finding.get('message', '-')}"
                )
    return "\n".join(lines) + "\n"


def build_sync_repair_report(
    loaded: LoadedConfig,
    *,
    dry_run: bool,
    output_path: Path | None = None,
    formats: tuple[str, ...] = ("json",),
    issue_id: int | None = None,
    tracker: str | None = None,
) -> SyncRepairReportBuildResult:
    normalized_formats = normalize_sync_manifest_report_formats(formats)
    default_name = "sync-repair-preview.json" if dry_run else "sync-repair-result.json"
    target = output_path or (loaded.reports_dir / default_name)
    export_paths = resolve_sync_manifest_report_export_paths(target, normalized_formats)
    snapshot = build_sync_repair_snapshot(
        loaded,
        dry_run=dry_run,
        issue_id=issue_id,
        tracker=tracker,
    )
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_sync_repair_json(snapshot))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_sync_repair_markdown(snapshot))
    summary = _mapping(snapshot, "summary")
    return SyncRepairReportBuildResult(
        output_paths=export_paths,
        overall_status=str(summary.get("overall_status", "clean")),
        total_reports=int(summary.get("total_reports", 0)),
        changed_reports=int(summary.get("changed_reports", 0)),
        findings_before=int(summary.get("findings_before", 0)),
        findings_after=int(summary.get("findings_after", 0)),
        dropped_entries=int(summary.get("dropped_entries", 0)),
        adopted_archives=int(summary.get("adopted_archives", 0)),
        normalized_entries=int(summary.get("normalized_entries", 0)),
    )


def build_sync_repair_snapshot(
    loaded: LoadedConfig,
    *,
    dry_run: bool,
    issue_id: int | None = None,
    tracker: str | None = None,
) -> dict[str, object]:
    results = repair_applied_sync_manifests(
        loaded,
        issue_id=issue_id,
        tracker=tracker,
        dry_run=dry_run,
    )
    changed_reports = sum(1 for result in results if result.changed)
    findings_before = sum(result.findings_before for result in results)
    findings_after = sum(result.findings_after for result in results)
    dropped_entries = sum(result.dropped_entries for result in results)
    adopted_archives = sum(result.adopted_archives for result in results)
    normalized_entries = sum(result.normalized_entries for result in results)
    return {
        "meta": {
            "rendered_at": utc_now().isoformat(),
            "repo_root": str(loaded.repo_root),
            "config_path": str(loaded.config_path),
            "issue_filter": issue_id,
            "tracker_filter": tracker,
            "mode": "preview" if dry_run else "applied",
            "dry_run": dry_run,
        },
        "summary": {
            "overall_status": _sync_repair_status(
                dry_run=dry_run,
                changed_reports=changed_reports,
                findings_after=findings_after,
            ),
            "total_reports": len(results),
            "changed_reports": changed_reports,
            "unchanged_reports": sum(1 for result in results if not result.changed),
            "findings_before": findings_before,
            "findings_after": findings_after,
            "dropped_entries": dropped_entries,
            "adopted_archives": adopted_archives,
            "normalized_entries": normalized_entries,
        },
        "results": [
            serialize_sync_manifest_repair_result(result, include_issue_root=True)
            for result in results
        ],
    }


def render_sync_repair_json(snapshot: dict[str, object]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


def render_sync_repair_markdown(snapshot: dict[str, object]) -> str:
    meta = _mapping(snapshot, "meta")
    summary = _mapping(snapshot, "summary")
    results = _list_of_dicts(snapshot.get("results"))
    title = "RepoRepublic Sync Repair Preview" if meta.get("dry_run") else "RepoRepublic Sync Repair Result"
    lines = [
        f"# {title}",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- config_path: {meta.get('config_path', '-')}",
        f"- issue_filter: {meta.get('issue_filter') if meta.get('issue_filter') is not None else 'all'}",
        f"- tracker_filter: {meta.get('tracker_filter') or 'all'}",
        f"- mode: {meta.get('mode', '-')}",
        "",
        "## Summary",
        f"- overall_status: {summary.get('overall_status', '-')}",
        f"- total_reports: {summary.get('total_reports', 0)}",
        f"- changed_reports: {summary.get('changed_reports', 0)}",
        f"- unchanged_reports: {summary.get('unchanged_reports', 0)}",
        f"- findings_before: {summary.get('findings_before', 0)}",
        f"- findings_after: {summary.get('findings_after', 0)}",
        f"- dropped_entries: {summary.get('dropped_entries', 0)}",
        f"- adopted_archives: {summary.get('adopted_archives', 0)}",
        f"- normalized_entries: {summary.get('normalized_entries', 0)}",
        "",
        "## Results",
    ]
    if not results:
        lines.append("- No applied sync manifests found.")
        return "\n".join(lines) + "\n"
    for result in results:
        issue_label = result.get("issue_id")
        lines.extend(
            [
                "",
                f"### {result.get('tracker', '-')} · issue #{issue_label if issue_label is not None else 'unknown'}",
                f"- status: {result.get('status', '-')}",
                f"- issue_root: {result.get('issue_root', '-')}",
                f"- manifest_path: {result.get('manifest_path', '-')}",
                f"- changed: {result.get('changed', False)}",
                f"- dry_run: {result.get('dry_run', False)}",
                f"- manifest_entries: {result.get('manifest_entry_count_before', 0)} -> {result.get('manifest_entry_count_after', 0)}",
                f"- findings: {result.get('findings_before', 0)} -> {result.get('findings_after', 0)}",
                f"- dropped_entries: {result.get('dropped_entries', 0)}",
                f"- adopted_archives: {result.get('adopted_archives', 0)}",
                f"- normalized_entries: {result.get('normalized_entries', 0)}",
            ]
        )
    return "\n".join(lines) + "\n"


def serialize_sync_manifest_report(
    report: AppliedSyncManifestReport,
    *,
    include_issue_root: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "tracker": report.tracker,
        "issue_id": report.issue_id,
        "status": "issues" if report.findings else "ok",
        "manifest_path": str(report.manifest_path),
        "manifest_exists": report.manifest_exists,
        "manifest_entry_count": report.manifest_entry_count,
        "archive_file_count": len(report.archive_files),
        "archive_files": list(report.archive_files),
        "referenced_archive_count": report.referenced_archive_count,
        "finding_count": len(report.findings),
        "findings": [serialize_sync_manifest_finding(finding) for finding in report.findings],
    }
    if include_issue_root:
        payload["issue_root"] = str(report.issue_root)
    return payload


def serialize_sync_manifest_finding(finding: AppliedSyncManifestFinding) -> dict[str, object]:
    return {
        "code": finding.code,
        "message": finding.message,
        "entry_key": finding.entry_key,
        "path": finding.path,
    }


def serialize_sync_manifest_repair_result(
    result: AppliedSyncManifestRepairResult,
    *,
    include_issue_root: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "tracker": result.tracker,
        "issue_id": result.issue_id,
        "status": _serialize_sync_repair_result_status(result),
        "manifest_path": str(result.manifest_path),
        "changed": result.changed,
        "dry_run": result.dry_run,
        "manifest_entry_count_before": result.manifest_entry_count_before,
        "manifest_entry_count_after": result.manifest_entry_count_after,
        "findings_before": result.findings_before,
        "findings_after": result.findings_after,
        "dropped_entries": result.dropped_entries,
        "adopted_archives": result.adopted_archives,
        "normalized_entries": result.normalized_entries,
    }
    if include_issue_root:
        payload["issue_root"] = str(result.issue_root)
    return payload


def _serialize_sync_repair_result_status(result: AppliedSyncManifestRepairResult) -> str:
    if result.findings_after:
        return "issues"
    if result.changed:
        return "changed" if result.dry_run else "repaired"
    return "unchanged"


def _sync_repair_status(
    *,
    dry_run: bool,
    changed_reports: int,
    findings_after: int,
) -> str:
    if findings_after:
        return "issues"
    if changed_reports:
        return "preview" if dry_run else "cleaned"
    return "clean"


def _mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _render_mapping(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    parts = [f"{key}={value[key]}" for key in sorted(value)]
    return ", ".join(parts)
