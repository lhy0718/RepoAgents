from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repoagents.utils.files import write_text_file


VALID_OPERATOR_REPORT_FORMATS = ("json", "markdown")


@dataclass(frozen=True, slots=True)
class OperatorReportBuildResult:
    output_paths: dict[str, Path]
    kind: str


def normalize_operator_report_formats(
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
            for item in VALID_OPERATOR_REPORT_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_OPERATOR_REPORT_FORMATS:
            raise ValueError(
                "Unsupported operator report format. Expected one of: json, markdown, all"
            )
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def resolve_operator_report_export_paths(
    target: Path,
    formats: tuple[str, ...],
) -> dict[str, Path]:
    export_paths: dict[str, Path] = {}
    resolved = target.resolve()
    for export_format in formats:
        suffix = ".md" if export_format == "markdown" else ".json"
        export_paths[export_format] = resolved.with_suffix(suffix)
    return export_paths


def build_operator_report_exports(
    *,
    kind: str,
    snapshot: dict[str, Any],
    output_path: Path,
    formats: tuple[str, ...],
) -> OperatorReportBuildResult:
    export_paths = resolve_operator_report_export_paths(output_path, formats)
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_operator_report_json(snapshot))
    if "markdown" in export_paths:
        markdown = (
            render_doctor_report_markdown(snapshot)
            if kind == "doctor"
            else render_status_report_markdown(snapshot)
        )
        write_text_file(export_paths["markdown"], markdown)
    return OperatorReportBuildResult(output_paths=export_paths, kind=kind)


def render_operator_report_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True)


def render_doctor_report_markdown(snapshot: dict[str, Any]) -> str:
    meta = _mapping(snapshot, "meta")
    summary = _mapping(snapshot, "summary")
    config = _mapping(snapshot, "config")
    codex = _mapping(snapshot, "codex")
    tracker = _mapping(snapshot, "tracker")
    workspace = _mapping(snapshot, "workspace")
    logging = _mapping(snapshot, "logging")
    managed_files = _mapping(snapshot, "managed_files")
    diagnostics = _list(snapshot.get("diagnostics"))

    lines = [
        "# Doctor report",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- overall_status: {summary.get('overall_status', '-')}",
        f"- exit_code: {summary.get('exit_code', '-')}",
        "",
        "## Config",
        f"- status: {config.get('status', '-')}",
        f"- path: {config.get('path', '-')}",
    ]
    if config.get("error"):
        lines.append(f"- error: {config['error']}")

    lines.extend(
        [
            "",
            "## Codex command",
            f"- command: {codex.get('command', '-')}",
            f"- status: {codex.get('status', '-')}",
            f"- path: {codex.get('path', '-')}",
            f"- version: {codex.get('version', '-')}",
        ]
    )

    if tracker:
        lines.extend(
            [
                "",
                "## Tracker",
                f"- kind: {tracker.get('kind', '-')}",
                f"- mode: {tracker.get('mode', '-')}",
                f"- repo: {tracker.get('repo', '-')}",
                f"- path: {tracker.get('path', '-')}",
                f"- poll_interval_seconds: {tracker.get('poll_interval_seconds', '-')}",
            ]
        )
        if "path_status" in tracker:
            lines.append(f"- path_status: {tracker.get('path_status', '-')}")

    if workspace:
        lines.extend(
            [
                "",
                "## Workspace",
                f"- strategy: {workspace.get('strategy', '-')}",
                f"- root: {workspace.get('root', '-')}",
                f"- dirty_policy: {workspace.get('dirty_policy', '-')}",
                f"- git_repo: {workspace.get('is_git_repo', '-')}",
                f"- working_tree_status: {workspace.get('working_tree_status', '-')}",
            ]
        )
        dirty_entries = _list(workspace.get("dirty_entries"))
        if dirty_entries:
            lines.append("- dirty_entries:")
            lines.extend(f"  - {entry}" for entry in dirty_entries)

    if logging:
        lines.extend(
            [
                "",
                "## Logging",
                f"- json_logs: {logging.get('json_logs', '-')}",
                f"- file_enabled: {logging.get('file_enabled', '-')}",
                f"- directory: {logging.get('directory', '-')}",
            ]
        )

    if managed_files:
        lines.extend(
            [
                "",
                "## Managed files",
                f"- status: {managed_files.get('status', '-')}",
                f"- required_count: {managed_files.get('required_count', '-')}",
                f"- missing_count: {managed_files.get('missing_count', '-')}",
            ]
        )
        missing = _list(managed_files.get("missing"))
        if missing:
            lines.append("- missing:")
            lines.extend(f"  - {path}" for path in missing)

    lines.extend(["", "## Diagnostics"])
    if not diagnostics:
        lines.append("- none")
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                "",
                f"### {item.get('name', 'Unknown check')}",
                f"- status: {item.get('status', '-')}",
                f"- message: {item.get('message', '-')}",
            ]
        )
        if item.get("hint"):
            lines.append(f"- hint: {item['hint']}")
        for detail in _list(item.get("detail_lines")):
            lines.append(f"  {detail}")
    return "\n".join(lines) + "\n"


def render_status_report_markdown(snapshot: dict[str, Any]) -> str:
    meta = _mapping(snapshot, "meta")
    summary = _mapping(snapshot, "summary")
    report_health = _mapping(snapshot, "report_health")
    hero = _mapping(report_health, "hero")
    policy = _mapping(report_health, "policy")
    reports = _mapping(report_health, "reports")
    policy_alignment = _mapping(report_health, "policy_alignment")
    policy_health = _mapping(report_health, "policy_health")
    ops_snapshots = _mapping(snapshot, "ops_snapshots")
    runs = _list(snapshot.get("runs"))

    lines = [
        "# Status report",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- config_path: {meta.get('config_path', '-')}",
        f"- state_path: {meta.get('state_path', '-')}",
        f"- issue_filter: {meta.get('issue_filter', '-')}",
        "",
        "## Run summary",
        f"- total_runs: {summary.get('total_runs', 0)}",
        f"- selected_runs: {summary.get('selected_runs', 0)}",
    ]
    selected_by_status = _mapping(summary, "selected_by_status")
    if selected_by_status:
        lines.append("- selected_by_status:")
        lines.extend(f"  - {key}: {value}" for key, value in selected_by_status.items())

    lines.extend(
        [
            "",
            "## Report health",
            f"- severity: {hero.get('severity', '-')}",
            f"- title: {hero.get('title', '-')}",
            f"- policy: {policy.get('summary', '-')}",
            f"- policy_health: {policy_health.get('severity', '-')} | {policy_health.get('message', '-')}",
            f"- policy_alignment_status: {policy_alignment.get('status', '-')}",
            f"- policy_mismatch_count: {policy_alignment.get('mismatch_count', 0)}",
            f"- overall_freshness_severity: {reports.get('freshness_severity', '-')}",
            f"- cleanup_freshness_severity: {reports.get('cleanup_freshness_severity', '-')}",
        ]
    )
    for detail in _list(policy_alignment.get("detail_lines")):
        lines.append(f"  {detail}")

    lines.extend(
        [
            "",
            "## Ops snapshots",
            f"- status: {ops_snapshots.get('status', '-')}",
            f"- history_entry_count: {ops_snapshots.get('history_entry_count', 0)}",
            f"- history_limit: {ops_snapshots.get('history_limit', 0)}",
            f"- dropped_entry_count: {ops_snapshots.get('dropped_entry_count', 0)}",
            f"- archive_entry_count: {ops_snapshots.get('archive_entry_count', 0)}",
        ]
    )
    latest_ops = _mapping(ops_snapshots, "latest")
    if latest_ops:
        lines.extend(
            [
                "- latest:",
                f"  - entry_id: {latest_ops.get('entry_id', '-')}",
                f"  - overall_status: {latest_ops.get('overall_status', '-')}",
                f"  - rendered_at: {latest_ops.get('rendered_at', '-')}",
                f"  - age_human: {latest_ops.get('age_human', '-')}",
                f"  - bundle_dir: {latest_ops.get('bundle_dir', '-')}",
                f"  - archive_path: {latest_ops.get('archive_path', '-')}",
            ]
        )

    lines.extend(["", "## Runs"])
    if not runs:
        lines.append("- none")
    for item in runs:
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                "",
                f"### Issue #{item.get('issue_id', '-')}",
                f"- run_id: {item.get('run_id', '-')}",
                f"- status: {item.get('status', '-')}",
                f"- attempts: {item.get('attempts', '-')}",
                f"- backend_mode: {item.get('backend_mode', '-')}",
                f"- current_role: {item.get('current_role', '-')}",
                f"- updated_at: {item.get('updated_at', '-')}",
            ]
        )
        if item.get("workspace_path"):
            lines.append(f"- workspace_path: {item['workspace_path']}")
        if item.get("next_retry_at"):
            lines.append(f"- next_retry_at: {item['next_retry_at']}")
        if item.get("summary"):
            lines.append(f"- summary: {item['summary']}")
        if item.get("last_error"):
            lines.append(f"- last_error: {item['last_error']}")
    return "\n".join(lines) + "\n"


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []
