from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from repoagents.dashboard import DashboardBuildResult
from repoagents.models.domain import utc_now
from repoagents.operator_reports import OperatorReportBuildResult
from repoagents.sync_audit import SyncAuditBuildResult
from repoagents.utils.files import write_text_file


@dataclass(frozen=True, slots=True)
class OpsSnapshotBundleResult:
    bundle_dir: Path
    overall_status: str
    component_statuses: dict[str, str]
    output_paths: dict[str, Path]


@dataclass(frozen=True, slots=True)
class OpsSnapshotArchiveResult:
    archive_path: Path
    sha256: str
    size_bytes: int
    file_count: int
    member_count: int


@dataclass(frozen=True, slots=True)
class OpsSnapshotIndexResult:
    latest_json: Path
    latest_markdown: Path
    history_json: Path
    history_markdown: Path
    history_limit: int
    entry_count: int
    dropped_entries: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class OpsSnapshotPruneResult:
    removed_bundle_dirs: tuple[Path, ...]
    removed_archives: tuple[Path, ...]
    skipped_external_paths: int
    skipped_active_paths: int
    missing_paths: int


OPS_SNAPSHOT_HISTORY_LIMIT = 25


def default_ops_snapshot_bundle_dir(reports_dir: Path) -> Path:
    timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return reports_dir / "ops" / timestamp


def default_ops_snapshot_archive_path(bundle_dir: Path) -> Path:
    resolved = bundle_dir.resolve()
    return resolved.parent / f"{resolved.name}.tar.gz"


def build_ops_snapshot_bundle(
    *,
    bundle_dir: Path,
    repo_root: Path,
    config_path: Path,
    issue_filter: int | None,
    tracker_filter: str | None,
    dashboard_limit: int,
    sync_limit: int,
    refresh_seconds: int,
    doctor_snapshot: dict[str, Any],
    doctor_result: OperatorReportBuildResult,
    status_snapshot: dict[str, Any],
    status_result: OperatorReportBuildResult,
    dashboard_result: DashboardBuildResult,
    sync_result: SyncAuditBuildResult,
    extra_components: dict[str, dict[str, Any]] | None = None,
) -> OpsSnapshotBundleResult:
    dashboard_snapshot = _load_json_snapshot(dashboard_result.exported_paths.get("json"))
    extra_components = extra_components or {}
    rendered_at = _first_string(
        _mapping(doctor_snapshot, "meta").get("rendered_at"),
        _mapping(status_snapshot, "meta").get("rendered_at"),
        _mapping(dashboard_snapshot, "meta").get("rendered_at"),
    )
    component_statuses = {
        "doctor": _normalize_status(_mapping(doctor_snapshot, "summary").get("overall_status")),
        "status": _normalize_status(_mapping(_mapping(status_snapshot, "report_health"), "hero").get("severity")),
        "dashboard": _normalize_status(_mapping(dashboard_snapshot, "hero").get("severity")),
        "sync_audit": _normalize_status(sync_result.overall_status),
    }
    for key, component in extra_components.items():
        component_statuses[key] = _normalize_status(component.get("status"))
    overall_status = _combine_statuses(component_statuses.values())

    payload = {
        "meta": {
            "rendered_at": rendered_at,
            "repo_root": str(repo_root),
            "config_path": str(config_path),
            "bundle_dir": str(bundle_dir),
            "issue_filter": issue_filter,
            "tracker_filter": tracker_filter,
            "dashboard_limit": dashboard_limit,
            "sync_limit": sync_limit,
            "refresh_seconds": refresh_seconds,
        },
        "summary": {
            "overall_status": overall_status,
            "component_statuses": component_statuses,
        },
        "handoff_brief": _build_handoff_brief_snapshot(extra_components.get("ops_brief")),
        "components": {
            "doctor": {
                "status": component_statuses["doctor"],
                "output_paths": _stringify_paths(doctor_result.output_paths),
                "diagnostic_count": _mapping(doctor_snapshot, "summary").get("diagnostic_count", 0),
                "exit_code": _mapping(doctor_snapshot, "summary").get("exit_code", 1),
            },
            "status": {
                "status": component_statuses["status"],
                "output_paths": _stringify_paths(status_result.output_paths),
                "total_runs": _mapping(status_snapshot, "summary").get("total_runs", 0),
                "selected_runs": _mapping(status_snapshot, "summary").get("selected_runs", 0),
                "report_health_severity": _mapping(_mapping(status_snapshot, "report_health"), "hero").get("severity", "unknown"),
            },
            "dashboard": {
                "status": component_statuses["dashboard"],
                "output_paths": _stringify_paths(dashboard_result.exported_paths),
                "total_runs": dashboard_result.total_runs,
                "visible_runs": dashboard_result.visible_runs,
                "report_health_severity": _mapping(dashboard_snapshot, "hero").get("severity", "unknown"),
                "available_reports": _mapping(_mapping(dashboard_snapshot, "counts"), "available_reports")
                or _mapping(dashboard_snapshot, "counts").get("available_reports", 0),
            },
            "sync_audit": {
                "status": component_statuses["sync_audit"],
                "output_paths": _stringify_paths(sync_result.output_paths),
                "overall_status": sync_result.overall_status,
                "pending_artifacts": sync_result.pending_artifacts,
                "integrity_issue_count": sync_result.integrity_issue_count,
                "prunable_groups": sync_result.prunable_groups,
                "related_cleanup_reports": sync_result.related_cleanup_reports,
            },
        },
        "cross_links": _build_cross_links(
            sync_output_paths=sync_result.output_paths,
            extra_components=extra_components,
        ),
    }
    for key, component in extra_components.items():
        payload["components"][key] = _serialize_extra_component(
            status=component_statuses[key],
            component=component,
        )

    manifest_json = bundle_dir / "bundle.json"
    manifest_markdown = bundle_dir / "bundle.md"
    landing_html = bundle_dir / "index.html"
    landing_markdown = bundle_dir / "README.md"
    payload["landing"] = {
        "html_path": str(landing_html),
        "markdown_path": str(landing_markdown),
        "bundle_json_path": str(manifest_json),
        "bundle_markdown_path": str(manifest_markdown),
    }
    write_text_file(manifest_json, json.dumps(payload, indent=2, sort_keys=True))
    write_text_file(manifest_markdown, render_ops_snapshot_bundle_markdown(payload))
    write_text_file(landing_html, render_ops_snapshot_landing_html(payload))
    write_text_file(landing_markdown, render_ops_snapshot_landing_markdown(payload))

    output_paths = {
        "bundle_json": manifest_json,
        "bundle_markdown": manifest_markdown,
        "landing_html": landing_html,
        "landing_markdown": landing_markdown,
        "doctor_json": doctor_result.output_paths.get("json"),
        "doctor_markdown": doctor_result.output_paths.get("markdown"),
        "status_json": status_result.output_paths.get("json"),
        "status_markdown": status_result.output_paths.get("markdown"),
        "dashboard_json": dashboard_result.exported_paths.get("json"),
        "dashboard_markdown": dashboard_result.exported_paths.get("markdown"),
        "sync_audit_json": sync_result.output_paths.get("json"),
        "sync_audit_markdown": sync_result.output_paths.get("markdown"),
    }
    for key, component in extra_components.items():
        component_paths = component.get("output_paths")
        if not isinstance(component_paths, dict):
            continue
        for export_name, export_path in component_paths.items():
            if isinstance(export_path, Path):
                output_paths[f"{key}_{export_name}"] = export_path
    return OpsSnapshotBundleResult(
        bundle_dir=bundle_dir,
        overall_status=overall_status,
        component_statuses=component_statuses,
        output_paths={key: value for key, value in output_paths.items() if value is not None},
    )


def build_ops_snapshot_archive(
    *,
    bundle_dir: Path,
    output_path: Path | None = None,
) -> OpsSnapshotArchiveResult:
    resolved_bundle_dir = bundle_dir.resolve()
    if not resolved_bundle_dir.exists() or not resolved_bundle_dir.is_dir():
        raise ValueError(f"Ops snapshot bundle directory does not exist: {resolved_bundle_dir}")
    archive_path = _resolve_ops_snapshot_archive_path(resolved_bundle_dir, output_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz", format=tarfile.PAX_FORMAT) as bundle_archive:
        bundle_archive.add(resolved_bundle_dir, arcname=resolved_bundle_dir.name)
    file_count = sum(1 for path in resolved_bundle_dir.rglob("*") if path.is_file())
    with tarfile.open(archive_path, "r:gz") as bundle_archive:
        member_count = len(bundle_archive.getmembers())
    return OpsSnapshotArchiveResult(
        archive_path=archive_path,
        sha256=_sha256_file(archive_path),
        size_bytes=archive_path.stat().st_size,
        file_count=file_count,
        member_count=member_count,
    )


def build_ops_snapshot_index(
    *,
    ops_root: Path,
    bundle_result: OpsSnapshotBundleResult,
    archive_result: OpsSnapshotArchiveResult | None = None,
    history_limit: int = OPS_SNAPSHOT_HISTORY_LIMIT,
    additional_dropped_entries: tuple[dict[str, Any], ...] = (),
) -> OpsSnapshotIndexResult:
    resolved_ops_root = ops_root.resolve()
    resolved_ops_root.mkdir(parents=True, exist_ok=True)
    latest_json = resolved_ops_root / "latest.json"
    latest_markdown = resolved_ops_root / "latest.md"
    history_json = resolved_ops_root / "history.json"
    history_markdown = resolved_ops_root / "history.md"

    entry = _build_ops_snapshot_index_entry(
        ops_root=resolved_ops_root,
        bundle_result=bundle_result,
        archive_result=archive_result,
    )
    history_payload = _load_ops_snapshot_history(history_json)
    existing_entries = _list(history_payload.get("entries"))
    filtered_entries = [
        item
        for item in existing_entries
        if isinstance(item, dict) and item.get("entry_id") != entry["entry_id"]
    ]
    bounded_limit = max(1, history_limit)
    combined_entries = [entry, *filtered_entries]
    entries = combined_entries[:bounded_limit]
    dropped_entries = _merge_ops_snapshot_dropped_entries(
        additional_dropped_entries,
        tuple(item for item in combined_entries[bounded_limit:] if isinstance(item, dict)),
    )
    latest_payload = {
        "meta": {
            "generated_at": utc_now().isoformat(),
            "ops_root": str(resolved_ops_root),
            "entry_count": len(entries),
            "history_limit": bounded_limit,
            "dropped_entry_count": len(dropped_entries),
        },
        "latest": entry,
    }
    history_snapshot = {
        "meta": {
            "generated_at": utc_now().isoformat(),
            "ops_root": str(resolved_ops_root),
            "history_limit": bounded_limit,
            "entry_count": len(entries),
            "dropped_entry_count": len(dropped_entries),
        },
        "latest_entry_id": entry["entry_id"],
        "entries": entries,
    }
    write_text_file(latest_json, json.dumps(latest_payload, indent=2, sort_keys=True))
    write_text_file(latest_markdown, render_ops_snapshot_latest_markdown(latest_payload))
    write_text_file(history_json, json.dumps(history_snapshot, indent=2, sort_keys=True))
    write_text_file(history_markdown, render_ops_snapshot_history_markdown(history_snapshot))
    return OpsSnapshotIndexResult(
        latest_json=latest_json,
        latest_markdown=latest_markdown,
        history_json=history_json,
        history_markdown=history_markdown,
        history_limit=bounded_limit,
        entry_count=len(entries),
        dropped_entries=dropped_entries,
    )


def _merge_ops_snapshot_dropped_entries(
    *entry_groups: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    merged: list[dict[str, Any]] = []
    seen_entry_ids: set[str] = set()
    for entries in entry_groups:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("entry_id")
            if isinstance(entry_id, str) and entry_id:
                if entry_id in seen_entry_ids:
                    continue
                seen_entry_ids.add(entry_id)
            merged.append(entry)
    return tuple(merged)


def prune_ops_snapshot_history(
    *,
    ops_root: Path,
    dropped_entries: tuple[dict[str, Any], ...],
) -> OpsSnapshotPruneResult:
    resolved_ops_root = ops_root.resolve()
    active_payload = _load_ops_snapshot_history(resolved_ops_root / "history.json")
    active_paths = _collect_active_managed_ops_paths(resolved_ops_root, active_payload)

    removed_bundle_dirs: list[Path] = []
    removed_archives: list[Path] = []
    skipped_external_paths = 0
    skipped_active_paths = 0
    missing_paths = 0
    seen_paths: set[tuple[str, Path]] = set()

    for entry in dropped_entries:
        for kind, candidate_path in _iter_ops_snapshot_entry_cleanup_paths(entry):
            if candidate_path is None:
                continue
            resolved_path = candidate_path.resolve()
            dedupe_key = (kind, resolved_path)
            if dedupe_key in seen_paths:
                continue
            seen_paths.add(dedupe_key)
            if not _is_path_within_root(resolved_path, resolved_ops_root):
                skipped_external_paths += 1
                continue
            if resolved_path in active_paths:
                skipped_active_paths += 1
                continue
            if not resolved_path.exists():
                missing_paths += 1
                continue
            if kind == "bundle_dir":
                shutil.rmtree(resolved_path)
                removed_bundle_dirs.append(resolved_path)
                continue
            resolved_path.unlink()
            removed_archives.append(resolved_path)

    return OpsSnapshotPruneResult(
        removed_bundle_dirs=tuple(removed_bundle_dirs),
        removed_archives=tuple(removed_archives),
        skipped_external_paths=skipped_external_paths,
        skipped_active_paths=skipped_active_paths,
        missing_paths=missing_paths,
    )


def render_ops_snapshot_bundle_markdown(payload: dict[str, Any]) -> str:
    meta = _mapping(payload, "meta")
    summary = _mapping(payload, "summary")
    handoff_brief = _mapping(payload, "handoff_brief")
    landing = _mapping(payload, "landing")
    components = _mapping(payload, "components")
    cross_links = _list(payload.get("cross_links"))
    lines = [
        "# RepoAgents Ops Snapshot Bundle",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- config_path: {meta.get('config_path', '-')}",
        f"- bundle_dir: {meta.get('bundle_dir', '-')}",
        f"- issue_filter: {meta.get('issue_filter', '-')}",
        f"- tracker_filter: {meta.get('tracker_filter', '-')}",
        f"- dashboard_limit: {meta.get('dashboard_limit', '-')}",
        f"- sync_limit: {meta.get('sync_limit', '-')}",
        f"- refresh_seconds: {meta.get('refresh_seconds', '-')}",
        "",
        "## Summary",
        f"- overall_status: {summary.get('overall_status', '-')}",
    ]
    component_statuses = _mapping(summary, "component_statuses")
    if component_statuses:
        lines.append("- component_statuses:")
        lines.extend(f"  - {name}: {status}" for name, status in component_statuses.items())
    if handoff_brief:
        lines.extend(
            [
                "",
                "## Handoff brief",
                f"- severity: {handoff_brief.get('severity', '-')}",
                f"- headline: {handoff_brief.get('headline', '-')}",
                f"- top_finding_count: {handoff_brief.get('top_finding_count', 0)}",
                f"- next_action_count: {handoff_brief.get('next_action_count', 0)}",
            ]
        )
        top_findings = _list(handoff_brief.get("top_findings"))
        if top_findings:
            lines.append("- top_findings:")
            lines.extend(f"  - {item}" for item in top_findings if isinstance(item, str))
        next_actions = _list(handoff_brief.get("next_actions"))
        if next_actions:
            lines.append("- next_actions:")
            lines.extend(f"  - {item}" for item in next_actions if isinstance(item, str))
    if landing:
        lines.extend(
            [
                "",
                "## Landing",
                f"- html_path: {landing.get('html_path', '-')}",
                f"- markdown_path: {landing.get('markdown_path', '-')}",
                f"- bundle_json_path: {landing.get('bundle_json_path', '-')}",
                f"- bundle_markdown_path: {landing.get('bundle_markdown_path', '-')}",
            ]
        )

    ordered_component_keys = ["doctor", "status", "dashboard", "github_smoke", "sync_audit"]
    ordered_component_keys.extend(
        key for key in components.keys() if key not in ordered_component_keys
    )
    for key in ordered_component_keys:
        component = _mapping(components, key)
        if not component:
            continue
        lines.extend(
            [
                "",
                f"## {key}",
                f"- status: {component.get('status', '-')}",
            ]
        )
        output_paths = _mapping(component, "output_paths")
        if output_paths:
            lines.append("- output_paths:")
            lines.extend(f"  - {name}: {path}" for name, path in output_paths.items())
        for field in (
            "diagnostic_count",
            "exit_code",
            "total_runs",
            "selected_runs",
            "report_health_severity",
            "visible_runs",
            "available_reports",
            "overall_status",
            "pending_artifacts",
            "open_issue_count",
            "sampled_issue_id",
            "repo_access_status",
            "default_branch",
            "branch_policy_status",
            "publish_status",
            "integrity_issue_count",
            "prunable_groups",
            "repair_needed_issues",
            "related_cleanup_reports",
            "related_report_mismatches",
            "related_report_policy_drifts",
            "headline",
            "top_finding_count",
            "mode",
            "action_count",
            "cleanup_action_count",
            "cleanup_sync_applied_action_count",
            "report_count",
            "issues_with_findings",
            "total_findings",
            "changed_reports",
            "unchanged_reports",
            "repair_changed_reports",
            "repair_findings_after",
            "findings_before",
            "findings_after",
            "dropped_entries",
            "adopted_archives",
            "normalized_entries",
            "related_sync_audit_reports",
            "sync_audit_policy_drifts",
            "next_action_count",
            "top_findings",
            "next_actions",
            "reason",
        ):
            if field in component:
                lines.append(f"- {field}: {component[field]}")
    if cross_links:
        lines.extend(["", "## Cross links"])
        for entry in cross_links:
            if not isinstance(entry, dict):
                continue
            lines.extend(
                [
                    "",
                    f"### {entry.get('source', '-')} -> {entry.get('target', '-')}",
                    f"- status: {entry.get('status', '-')}",
                    f"- reason: {entry.get('reason', '-')}",
                ]
            )
            source_paths = _mapping(entry, "source_paths")
            if source_paths:
                lines.append("- source_paths:")
                lines.extend(f"  - {name}: {path}" for name, path in source_paths.items())
            target_paths = _mapping(entry, "target_paths")
            if target_paths:
                lines.append("- target_paths:")
                lines.extend(f"  - {name}: {path}" for name, path in target_paths.items())
    return "\n".join(lines) + "\n"


def render_ops_snapshot_landing_markdown(payload: dict[str, Any]) -> str:
    meta = _mapping(payload, "meta")
    summary = _mapping(payload, "summary")
    handoff_brief = _mapping(payload, "handoff_brief")
    components = _mapping(payload, "components")
    landing = _mapping(payload, "landing")
    lines = [
        "# RepoAgents Ops Handoff",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- bundle_dir: {meta.get('bundle_dir', '-')}",
        f"- overall_status: {summary.get('overall_status', '-')}",
        "",
        "## Brief",
        f"- severity: {handoff_brief.get('severity', '-')}",
        f"- headline: {handoff_brief.get('headline', '-')}",
        f"- top_finding_count: {handoff_brief.get('top_finding_count', 0)}",
        f"- next_action_count: {handoff_brief.get('next_action_count', 0)}",
    ]
    top_findings = [item for item in _list(handoff_brief.get("top_findings")) if isinstance(item, str)]
    if top_findings:
        lines.append("- top_findings:")
        lines.extend(f"  - {item}" for item in top_findings)
    next_actions = [item for item in _list(handoff_brief.get("next_actions")) if isinstance(item, str)]
    if next_actions:
        lines.append("- next_actions:")
        lines.extend(f"  - {item}" for item in next_actions)
    lines.extend(["", "## Quick links"])
    link_items = [
        ("landing_html", landing.get("html_path")),
        ("bundle_json", landing.get("bundle_json_path")),
        ("bundle_markdown", landing.get("bundle_markdown_path")),
    ]
    for component_key in ("ops_brief", "ops_status", "dashboard", "github_smoke", "sync_health", "sync_audit", "doctor", "status"):
        component = _mapping(components, component_key)
        output_paths = _mapping(component, "output_paths")
        for name, path in output_paths.items():
            link_items.append((f"{component_key}_{name}", path))
    seen_links: set[tuple[str, str]] = set()
    for label, path in link_items:
        if not isinstance(path, str) or not path:
            continue
        dedupe_key = (label, path)
        if dedupe_key in seen_links:
            continue
        seen_links.add(dedupe_key)
        lines.append(f"- {label}: {path}")
    lines.extend(["", "## Component summary"])
    component_statuses = _mapping(summary, "component_statuses")
    if component_statuses:
        for name, status in component_statuses.items():
            lines.append(f"- {name}: {status}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def render_ops_snapshot_landing_html(payload: dict[str, Any]) -> str:
    meta = _mapping(payload, "meta")
    summary = _mapping(payload, "summary")
    handoff_brief = _mapping(payload, "handoff_brief")
    components = _mapping(payload, "components")
    landing = _mapping(payload, "landing")
    top_findings = [item for item in _list(handoff_brief.get("top_findings")) if isinstance(item, str)]
    next_actions = [item for item in _list(handoff_brief.get("next_actions")) if isinstance(item, str)]
    component_statuses = _mapping(summary, "component_statuses")
    quick_links: list[tuple[str, str]] = []
    for label, path in (
        ("bundle.json", landing.get("bundle_json_path")),
        ("bundle.md", landing.get("bundle_markdown_path")),
        ("ops-brief.json", _mapping(_mapping(components, "ops_brief"), "output_paths").get("json")),
        ("ops-brief.md", _mapping(_mapping(components, "ops_brief"), "output_paths").get("markdown")),
        ("ops-status.json", _mapping(_mapping(components, "ops_status"), "output_paths").get("json")),
        ("ops-status.md", _mapping(_mapping(components, "ops_status"), "output_paths").get("markdown")),
        ("dashboard.json", _mapping(_mapping(components, "dashboard"), "output_paths").get("json")),
        ("dashboard.md", _mapping(_mapping(components, "dashboard"), "output_paths").get("markdown")),
        ("github-smoke.json", _mapping(_mapping(components, "github_smoke"), "output_paths").get("json")),
        ("github-smoke.md", _mapping(_mapping(components, "github_smoke"), "output_paths").get("markdown")),
        ("sync-health.json", _mapping(_mapping(components, "sync_health"), "output_paths").get("json")),
        ("sync-audit.json", _mapping(_mapping(components, "sync_audit"), "output_paths").get("json")),
    ):
        if isinstance(path, str) and path:
            quick_links.append((label, Path(path).name))
    quick_link_markup = "".join(
        f'<li><a href="{escape(target)}">{escape(label)}</a></li>'
        for label, target in quick_links
    ) or "<li>none</li>"
    finding_markup = "".join(f"<li>{escape(item)}</li>" for item in top_findings) or "<li>No notable findings.</li>"
    action_markup = "".join(f"<li>{escape(item)}</li>" for item in next_actions) or "<li>No immediate follow-up actions.</li>"
    component_markup = "".join(
        f"<li><strong>{escape(str(name))}:</strong> {escape(str(status))}</li>"
        for name, status in component_statuses.items()
    ) or "<li>none</li>"
    overall_status = str(summary.get("overall_status", "attention"))
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\" />\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
        "  <title>RepoAgents Ops Handoff</title>\n"
        "  <style>\n"
        "    body { font-family: Georgia, 'Times New Roman', serif; margin: 2rem auto; max-width: 56rem; padding: 0 1.25rem; color: #1e2230; background: #f7f4ee; }\n"
        "    .hero { background: linear-gradient(135deg, #fbf0c7, #f2d2b2); border: 1px solid #c79c63; border-radius: 18px; padding: 1.5rem; }\n"
        "    .status { display: inline-block; margin-top: 0.5rem; padding: 0.2rem 0.6rem; border-radius: 999px; background: #1e2230; color: #fff; font-size: 0.85rem; }\n"
        "    h1, h2 { margin-bottom: 0.4rem; }\n"
        "    .grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); margin-top: 1rem; }\n"
        "    .panel { background: #fffdfa; border: 1px solid #dbcbb4; border-radius: 14px; padding: 1rem; }\n"
        "    code { background: #efe3d1; padding: 0.1rem 0.3rem; border-radius: 6px; }\n"
        "    ul { margin: 0.6rem 0 0; padding-left: 1.2rem; }\n"
        "    a { color: #8a3d18; }\n"
        "    .meta { color: #5d544b; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"  <section class=\"hero\">\n"
        f"    <p class=\"meta\">RepoAgents ops handoff</p>\n"
        f"    <h1>{escape(str(handoff_brief.get('headline', 'Ops snapshot handoff available.')))}</h1>\n"
        f"    <p>{escape(str(meta.get('repo_root', '-')))}</p>\n"
        f"    <span class=\"status\">{escape(overall_status)}</span>\n"
        "  </section>\n"
        "  <div class=\"grid\">\n"
        "    <section class=\"panel\">\n"
        "      <h2>Bundle</h2>\n"
        f"      <p><strong>rendered_at:</strong> {escape(str(meta.get('rendered_at', '-')))}</p>\n"
        f"      <p><strong>bundle_dir:</strong> <code>{escape(str(meta.get('bundle_dir', '-')))}</code></p>\n"
        f"      <p><strong>top_finding_count:</strong> {escape(str(handoff_brief.get('top_finding_count', 0)))}</p>\n"
        f"      <p><strong>next_action_count:</strong> {escape(str(handoff_brief.get('next_action_count', 0)))}</p>\n"
        "    </section>\n"
        "    <section class=\"panel\">\n"
        "      <h2>Quick links</h2>\n"
        f"      <ul>{quick_link_markup}</ul>\n"
        "    </section>\n"
        "  </div>\n"
        "  <div class=\"grid\">\n"
        "    <section class=\"panel\">\n"
        "      <h2>Top findings</h2>\n"
        f"      <ul>{finding_markup}</ul>\n"
        "    </section>\n"
        "    <section class=\"panel\">\n"
        "      <h2>Next actions</h2>\n"
        f"      <ul>{action_markup}</ul>\n"
        "    </section>\n"
        "  </div>\n"
        "  <section class=\"panel\" style=\"margin-top: 1rem;\">\n"
        "    <h2>Component status</h2>\n"
        f"    <ul>{component_markup}</ul>\n"
        "  </section>\n"
        "</body>\n"
        "</html>\n"
    )


def render_ops_snapshot_latest_markdown(payload: dict[str, Any]) -> str:
    meta = _mapping(payload, "meta")
    latest = _mapping(payload, "latest")
    lines = [
        "# RepoAgents Ops Snapshot Latest",
        "",
        f"- generated_at: {meta.get('generated_at', '-')}",
        f"- ops_root: {meta.get('ops_root', '-')}",
        f"- history_limit: {meta.get('history_limit', 0)}",
        f"- entry_count: {meta.get('entry_count', 0)}",
        f"- dropped_entry_count: {meta.get('dropped_entry_count', 0)}",
        "",
    ]
    lines.extend(_render_ops_snapshot_index_entry_markdown("Latest bundle", latest))
    return "\n".join(lines) + "\n"


def render_ops_snapshot_history_markdown(payload: dict[str, Any]) -> str:
    meta = _mapping(payload, "meta")
    entries = _list(payload.get("entries"))
    lines = [
        "# RepoAgents Ops Snapshot History",
        "",
        f"- generated_at: {meta.get('generated_at', '-')}",
        f"- ops_root: {meta.get('ops_root', '-')}",
        f"- history_limit: {meta.get('history_limit', 0)}",
        f"- entry_count: {meta.get('entry_count', 0)}",
        f"- dropped_entry_count: {meta.get('dropped_entry_count', 0)}",
    ]
    if not entries:
        lines.extend(["", "- No ops snapshot bundles recorded."])
        return "\n".join(lines) + "\n"
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        lines.extend(["", * _render_ops_snapshot_index_entry_markdown(f"Entry {index}", entry)])
    return "\n".join(lines) + "\n"


def _load_json_snapshot(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _load_ops_snapshot_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _collect_active_managed_ops_paths(ops_root: Path, payload: dict[str, Any]) -> set[Path]:
    active_paths: set[Path] = set()
    for entry in _list(payload.get("entries")):
        if not isinstance(entry, dict):
            continue
        for _, candidate_path in _iter_ops_snapshot_entry_cleanup_paths(entry):
            if candidate_path is None:
                continue
            resolved_path = candidate_path.resolve()
            if _is_path_within_root(resolved_path, ops_root):
                active_paths.add(resolved_path)
    return active_paths


def _iter_ops_snapshot_entry_cleanup_paths(entry: dict[str, Any]) -> list[tuple[str, Path | None]]:
    archive = entry.get("archive")
    archive_path = None
    if isinstance(archive, dict):
        archive_path = _coerce_path(archive.get("path"))
    return [
        ("bundle_dir", _coerce_path(entry.get("bundle_dir"))),
        ("archive", archive_path),
    ]


def _build_ops_snapshot_index_entry(
    *,
    ops_root: Path,
    bundle_result: OpsSnapshotBundleResult,
    archive_result: OpsSnapshotArchiveResult | None,
) -> dict[str, Any]:
    bundle_manifest = _load_json_snapshot(bundle_result.output_paths.get("bundle_json"))
    meta = _mapping(bundle_manifest, "meta")
    handoff_brief = _mapping(bundle_manifest, "handoff_brief")
    landing = _mapping(bundle_manifest, "landing")
    return {
        "entry_id": bundle_result.bundle_dir.name,
        "rendered_at": meta.get("rendered_at") or utc_now().isoformat(),
        "overall_status": bundle_result.overall_status,
        "issue_filter": meta.get("issue_filter"),
        "tracker_filter": meta.get("tracker_filter"),
        "bundle_dir": str(bundle_result.bundle_dir),
        "bundle_relative_dir": _relative_to_root(bundle_result.bundle_dir, ops_root),
        "bundle_json": _stringify_optional_path(bundle_result.output_paths.get("bundle_json")),
        "bundle_markdown": _stringify_optional_path(bundle_result.output_paths.get("bundle_markdown")),
        "landing_html": _stringify_optional_path(bundle_result.output_paths.get("landing_html"))
        or _string_or_none(landing.get("html_path")),
        "landing_markdown": _stringify_optional_path(bundle_result.output_paths.get("landing_markdown"))
        or _string_or_none(landing.get("markdown_path")),
        "brief_json": _stringify_optional_path(bundle_result.output_paths.get("ops_brief_json")),
        "brief_markdown": _stringify_optional_path(bundle_result.output_paths.get("ops_brief_markdown")),
        "brief_severity": handoff_brief.get("severity"),
        "brief_headline": handoff_brief.get("headline"),
        "brief_top_finding_count": handoff_brief.get("top_finding_count", 0),
        "brief_next_action_count": handoff_brief.get("next_action_count", 0),
        "archive": (
            {
                "path": str(archive_result.archive_path),
                "relative_path": _relative_to_root(archive_result.archive_path, ops_root),
                "sha256": archive_result.sha256,
                "size_bytes": archive_result.size_bytes,
                "file_count": archive_result.file_count,
                "member_count": archive_result.member_count,
            }
            if archive_result is not None
            else None
        ),
        "component_statuses": dict(sorted(bundle_result.component_statuses.items())),
    }


def _render_ops_snapshot_index_entry_markdown(title: str, entry: dict[str, Any]) -> list[str]:
    lines = [
        f"## {title}",
        f"- entry_id: {entry.get('entry_id', '-')}",
        f"- rendered_at: {entry.get('rendered_at', '-')}",
        f"- overall_status: {entry.get('overall_status', '-')}",
        f"- issue_filter: {entry.get('issue_filter', '-')}",
        f"- tracker_filter: {entry.get('tracker_filter', '-')}",
        f"- bundle_dir: {entry.get('bundle_dir', '-')}",
        f"- bundle_relative_dir: {entry.get('bundle_relative_dir', '-')}",
        f"- bundle_json: {entry.get('bundle_json', '-')}",
        f"- bundle_markdown: {entry.get('bundle_markdown', '-')}",
        f"- landing_html: {entry.get('landing_html', '-')}",
        f"- landing_markdown: {entry.get('landing_markdown', '-')}",
        f"- brief_json: {entry.get('brief_json', '-')}",
        f"- brief_markdown: {entry.get('brief_markdown', '-')}",
        f"- brief_severity: {entry.get('brief_severity', '-')}",
        f"- brief_headline: {entry.get('brief_headline', '-')}",
        f"- brief_top_finding_count: {entry.get('brief_top_finding_count', 0)}",
        f"- brief_next_action_count: {entry.get('brief_next_action_count', 0)}",
    ]
    component_statuses = entry.get("component_statuses")
    if isinstance(component_statuses, dict) and component_statuses:
        lines.append("- component_statuses:")
        lines.extend(f"  - {name}: {status}" for name, status in component_statuses.items())
    archive = entry.get("archive")
    if isinstance(archive, dict):
        lines.extend(
            [
                "- archive:",
                f"  - path: {archive.get('path', '-')}",
                f"  - relative_path: {archive.get('relative_path', '-')}",
                f"  - sha256: {archive.get('sha256', '-')}",
                f"  - size_bytes: {archive.get('size_bytes', '-')}",
                f"  - file_count: {archive.get('file_count', '-')}",
                f"  - member_count: {archive.get('member_count', '-')}",
            ]
        )
    return lines


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _stringify_paths(paths: dict[str, Path]) -> dict[str, str]:
    return {key: str(path) for key, path in paths.items()}


def _stringify_optional_path(path: Path | None) -> str | None:
    return str(path) if isinstance(path, Path) else None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _build_handoff_brief_snapshot(component: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(component, dict):
        return {}
    snapshot = {
        "severity": component.get("status", "attention"),
        "headline": component.get("headline"),
        "top_finding_count": component.get("top_finding_count", 0),
        "next_action_count": component.get("next_action_count", 0),
    }
    top_findings = component.get("top_findings")
    if isinstance(top_findings, list):
        snapshot["top_findings"] = [item for item in top_findings if isinstance(item, str)]
    next_actions = component.get("next_actions")
    if isinstance(next_actions, list):
        snapshot["next_actions"] = [item for item in next_actions if isinstance(item, str)]
    return snapshot


def _serialize_extra_component(
    *,
    status: str,
    component: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status}
    for key, value in component.items():
        if key == "status":
            continue
        if key == "output_paths" and isinstance(value, dict):
            payload[key] = _stringify_paths({name: path for name, path in value.items() if isinstance(path, Path)})
            continue
        if key in {"link_to_sync_audit", "link_targets"}:
            continue
        payload[key] = value
    return payload


def _build_cross_links(
    *,
    sync_output_paths: dict[str, Path],
    extra_components: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    available_paths: dict[str, dict[str, Path]] = {"sync_audit": dict(sync_output_paths)}
    for key, component in extra_components.items():
        component_paths = component.get("output_paths")
        if not isinstance(component_paths, dict):
            continue
        valid_component_paths = {
            name: path for name, path in component_paths.items() if isinstance(path, Path)
        }
        if valid_component_paths:
            available_paths[key] = valid_component_paths

    for key, component in extra_components.items():
        source_paths = available_paths.get(key)
        if not source_paths:
            continue
        raw_targets = component.get("link_targets")
        target_names: list[str] = []
        if isinstance(raw_targets, (list, tuple)):
            for value in raw_targets:
                if isinstance(value, str) and value and value not in target_names:
                    target_names.append(value)
        elif component.get("link_to_sync_audit"):
            target_names.append("sync_audit")
        if not target_names:
            continue
        reason = str(component.get("reason") or "included in ops snapshot bundle")
        for target_name in target_names:
            target_paths = available_paths.get(target_name)
            if not target_paths:
                continue
            if (key, target_name) not in seen_pairs:
                links.append(
                    {
                        "source": key,
                        "target": target_name,
                        "status": "available",
                        "reason": reason,
                        "source_paths": _stringify_paths(source_paths),
                        "target_paths": _stringify_paths(target_paths),
                    }
                )
                seen_pairs.add((key, target_name))
            if (target_name, key) not in seen_pairs:
                links.append(
                    {
                        "source": target_name,
                        "target": key,
                        "status": "available",
                        "reason": "paired in ops snapshot bundle",
                        "source_paths": _stringify_paths(target_paths),
                        "target_paths": _stringify_paths(source_paths),
                    }
                )
                seen_pairs.add((target_name, key))
    return links


def _first_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return utc_now().isoformat()


def _resolve_ops_snapshot_archive_path(bundle_dir: Path, output_path: Path | None) -> Path:
    if output_path is None:
        return default_ops_snapshot_archive_path(bundle_dir)
    resolved = output_path.resolve()
    if resolved.exists() and resolved.is_dir():
        return resolved / f"{bundle_dir.name}.tar.gz"
    if resolved.name.endswith(".tar.gz") or resolved.suffix.lower() == ".tgz":
        return resolved
    return resolved.with_suffix(".tar.gz")


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _coerce_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


def _is_path_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_status(value: object) -> str:
    if not isinstance(value, str):
        return "attention"
    lowered = value.strip().lower()
    if lowered in {"issues", "error", "failed"}:
        return "issues"
    if lowered in {"attention", "warn", "warning", "preview"}:
        return "attention"
    if lowered in {"ok", "clean", "cleaned", "completed", "available"}:
        return "clean"
    return "attention"


def _combine_statuses(statuses: Any) -> str:
    normalized = {_normalize_status(value) for value in statuses}
    if "issues" in normalized:
        return "issues"
    if "attention" in normalized:
        return "attention"
    return "clean"


def _list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    return []
