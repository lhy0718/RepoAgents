from __future__ import annotations

import asyncio
from collections import Counter
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import httpx
import typer
import yaml

from repoagents import __version__
from repoagents.cleanup_report import (
    CleanupReportBuildResult,
    build_cleanup_report,
    normalize_cleanup_report_formats,
)
from repoagents.config import ConfigLoadError, LoadedConfig, load_config, resolve_repo_root
from repoagents.dashboard import (
    build_dashboard,
    build_ops_snapshot_status_snapshot,
    build_report_health_snapshot,
    normalize_dashboard_formats,
)
from repoagents.github_health import (
    build_github_smoke_exports,
    build_github_smoke_snapshot,
    collect_github_auth_snapshot,
    collect_github_live_repo_snapshots,
    collect_github_origin_snapshot,
    collect_github_publish_readiness,
    extract_git_remote_repo_slug,
    normalize_github_smoke_formats,
    render_github_smoke_text,
)
from repoagents.logging import configure_logging
from repoagents.models import RunLifecycle, RunRecord
from repoagents.models.domain import utc_now
from repoagents.operator_reports import (
    build_operator_report_exports,
    normalize_operator_report_formats,
)
from repoagents.ops_bundle import (
    build_ops_snapshot_index,
    build_ops_snapshot_bundle,
    build_ops_snapshot_archive,
    default_ops_snapshot_bundle_dir,
    prune_ops_snapshot_history,
)
from repoagents.ops_brief import (
    OpsBriefBuildResult,
    build_ops_brief_exports,
    build_ops_brief_snapshot,
)
from repoagents.ops_status import (
    OpsStatusBuildResult,
    build_ops_status_exports,
    build_ops_status_snapshot,
    normalize_ops_status_formats,
    render_ops_status_text,
)
from repoagents.orchestrator import DryRunPreview, Orchestrator, RunStateStore, load_webhook_payload
from repoagents._related_report_details.rendering import (
    build_related_report_detail_block,
    build_related_report_detail_line_layout,
    extract_related_report_warning_lines,
    render_related_report_detail_lines,
)
from repoagents.release_announcement import (
    build_release_announcement_exports,
    build_release_announcement_snapshot,
    normalize_release_announcement_formats,
    render_release_announcement_text,
)
from repoagents.release_assets import (
    build_release_asset_exports,
    build_release_asset_snapshot,
    normalize_release_asset_formats,
    render_release_asset_text,
)
from repoagents.release_checklist import (
    build_release_checklist_exports,
    build_release_checklist_snapshot,
    normalize_release_checklist_formats,
    render_release_checklist_text,
)
from repoagents.release_preview import (
    build_release_preview_exports,
    build_release_preview_snapshot,
    normalize_release_preview_formats,
    render_release_preview_text,
)
from repoagents.report_policy import build_report_policy_drift_guidance
from repoagents.sync_manifest_reports import (
    build_sync_check_report,
    build_sync_repair_report,
    serialize_sync_manifest_repair_result,
    serialize_sync_manifest_report,
)
from repoagents.sync_audit import (
    build_sync_audit_report,
    normalize_sync_audit_formats,
)
from repoagents.sync_health import (
    SyncHealthBuildResult,
    build_sync_health_report,
    build_sync_health_snapshot,
    normalize_sync_health_formats,
    render_sync_health_text,
)
from repoagents.sync_artifacts import (
    SyncArtifact,
    SyncArtifactLookupError,
    apply_sync_artifact,
    apply_sync_bundle,
    inspect_applied_sync_manifests,
    list_sync_artifacts,
    repair_applied_sync_manifests,
    resolve_sync_artifact,
)
from repoagents.tracker import build_tracker
from repoagents.templates import (
    PRESETS,
    apply_upgrade_plan,
    build_upgrade_plan,
    detect_scaffold_preset,
    extract_managed_block,
    render_agents_block,
    render_managed_file_map,
    scaffold_repository,
)
from repoagents.utils import (
    GitCommandError,
    ensure_dir,
    is_git_repository,
    list_dirty_working_tree_entries,
    run_git,
    write_json_file,
    write_text_file,
)
from repoagents.workspace import CopyWorkspaceManager, WorktreeWorkspaceManager


app = typer.Typer(
    name="repoagents",
    help="Install an AI maintainer team into any repo.",
    no_args_is_help=True,
)
sync_app = typer.Typer(help="Inspect staged tracker sync artifacts.")
ops_app = typer.Typer(help="Export operator snapshot bundles.")
github_app = typer.Typer(help="Inspect live GitHub tracker readiness.")
release_app = typer.Typer(help="Prepare public release preview artifacts.")
RAW_POLICY_REPORT_EXPORTS = (
    "sync-audit.json",
    "cleanup-preview.json",
    "cleanup-result.json",
)
INIT_PRESET_ORDER = ("none", "python-library", "web-app", "docs-only", "research-project")


@dataclass(frozen=True, slots=True)
class WorkingTreeStatus:
    is_git_repo: bool
    dirty_entries: list[str]


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    name: str
    status: str
    message: str
    hint: str | None = None
    detail_lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportPolicyMismatch:
    file_name: str
    embedded_summary: str
    current_summary: str


@dataclass(frozen=True, slots=True)
class ReportPolicyExportAlignment:
    current_summary: str
    comparable_reports: int
    mismatches: tuple[ReportPolicyMismatch, ...]


@dataclass(frozen=True, slots=True)
class ReportPolicyHealth:
    severity: str
    status: str
    message: str
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class CleanAction:
    kind: str
    path: Path
    issue_id: int | None = None
    run_id: str | None = None
    state_updated: bool = False
    replacement_payload: object | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    value: str
    label: str
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class GitHubRepoProbe:
    status: str
    message: str | None = None


def main() -> None:
    app()


@app.callback()
def callback() -> None:
    """RepoAgents CLI."""


app.add_typer(sync_app, name="sync")
app.add_typer(ops_app, name="ops")
app.add_typer(github_app, name="github")
app.add_typer(release_app, name="release")


@app.command("init")
def init_command(
    preset: str | None = typer.Option(
        None,
        "--preset",
        help="Bootstrap preset: none, python-library, web-app, docs-only, or research-project.",
    ),
    tracker_kind: str | None = typer.Option(
        None,
        "--tracker-kind",
        help="Tracker adapter kind: github, local_file, or local_markdown.",
    ),
    tracker_repo: str | None = typer.Option(
        None,
        "--tracker-repo",
        help="GitHub repo slug used by the issue tracker, for example owner/name.",
    ),
    tracker_path: str | None = typer.Option(
        None,
        "--tracker-path",
        help="Local issue path used by the local_file or local_markdown tracker.",
    ),
    fixture_issues: str | None = typer.Option(
        None,
        "--fixture-issues",
        help="Optional JSON file for local fixture issues.",
    ),
    interactive: bool | None = typer.Option(
        None,
        "--interactive/--no-interactive",
        help="Prompt for init options. Defaults to interactive mode when no init flags are provided.",
    ),
    upgrade: bool = typer.Option(
        False,
        "--upgrade",
        help="Refresh managed scaffold files using the current repo configuration.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite managed RepoAgents files."),
) -> None:
    repo_root = Path.cwd()
    if upgrade:
        upgrade_preset, resolved_tracker_kind, target_repo, resolved_tracker_path, resolved_fixture_issues = _resolve_upgrade_inputs(
            repo_root=repo_root,
            preset=preset,
            tracker_kind=tracker_kind,
            tracker_repo=tracker_repo,
            tracker_path=tracker_path,
            fixture_issues=fixture_issues,
        )
        plan = build_upgrade_plan(
            repo_root=repo_root,
            preset_name=upgrade_preset,
            tracker_repo=target_repo,
            fixture_issues=resolved_fixture_issues,
            force=force,
            tracker_kind=resolved_tracker_kind,
            tracker_path=resolved_tracker_path,
        )
        if not plan:
            typer.echo("No managed template updates detected.")
            return
        typer.echo(f"Upgrade plan for {repo_root}:")
        for item in plan:
            typer.echo(f"- {item.action}: {item.label} ({item.reason})")
            if item.diff_preview:
                typer.echo(_indent_block(item.diff_preview, prefix="    "))
        if any(item.action == "preserve" for item in plan) and not force:
            typer.echo(
                "Local modifications were preserved. Re-run with `repoagents init --upgrade --force` to overwrite drifted managed files."
            )
        updated = apply_upgrade_plan(plan)
        if updated:
            typer.echo("Applied upgrades:")
            for path in updated:
                typer.echo(f"- {path.relative_to(repo_root)}")
        return

    interactive_mode = _should_prompt_for_init(
        interactive,
        preset,
        tracker_kind,
        tracker_repo,
        tracker_path,
        fixture_issues,
    )
    if interactive_mode:
        typer.echo("Interactive RepoAgents initialization")
        (
            preset_name,
            resolved_tracker_kind,
            target_repo,
            resolved_tracker_path,
            resolved_fixture_issues,
        ) = _prompt_init_inputs(
            repo_root=repo_root,
            preset=preset,
            tracker_kind=tracker_kind,
            tracker_repo=tracker_repo,
            tracker_path=tracker_path,
            fixture_issues=fixture_issues,
        )
    else:
        preset_name = preset or "python-library"
        resolved_tracker_kind = _normalize_tracker_kind(tracker_kind or "github")
        if resolved_tracker_kind == "github":
            target_repo = tracker_repo or _default_github_tracker_repo(repo_root)
        else:
            target_repo = tracker_repo or f"local/{repo_root.name}"
        resolved_tracker_path = tracker_path or (
            "issues" if resolved_tracker_kind == "local_markdown" else "issues.json"
        )
        resolved_fixture_issues = fixture_issues if resolved_tracker_kind == "github" else None

    if preset_name not in PRESETS:
        typer.echo(
            f"Unknown preset '{preset_name}'. Available presets: {', '.join(sorted(PRESETS))}",
            err=True,
        )
        raise typer.Exit(code=2)
    created = scaffold_repository(
        repo_root=repo_root,
        preset_name=preset_name,
        tracker_repo=target_repo,
        fixture_issues=resolved_fixture_issues,
        force=force,
        tracker_kind=resolved_tracker_kind,
        tracker_path=resolved_tracker_path,
    )
    typer.echo(f"Initialized RepoAgents in {repo_root}")
    if created:
        typer.echo("Created or updated files:")
        for path in created:
            typer.echo(f"- {path.relative_to(repo_root)}")
    else:
        typer.echo("No files changed. Use --force to refresh managed templates.")


@app.command("doctor")
def doctor_command(
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text, json, markdown, or all.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional doctor report output path. Additional formats reuse the same filename stem.",
    ),
) -> None:
    repo_root = resolve_repo_root(Path.cwd())
    output_format = format.strip().lower()
    export_formats: tuple[str, ...] | None = None
    if output_format != "text":
        try:
            export_formats = normalize_operator_report_formats((output_format,))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--format") from exc

    config_status = None
    config_error: str | None = None
    try:
        loaded = load_config(repo_root)
        config_status = loaded
    except ConfigLoadError as exc:
        config_error = str(exc)
        loaded = None

    codex_command = loaded.data.codex.command if loaded else "codex"
    command_path = shutil.which(codex_command)
    codex_version: str | None = None
    if command_path:
        codex_version = _run_version([codex_command, "--version"]).strip()

    if export_formats is None:
        typer.echo(f"Repo root: {repo_root}")
        if config_status:
            typer.echo(f"Config: OK ({loaded.config_path})")
        else:
            typer.echo(f"Config: ERROR\n{config_error}", err=True)
    if command_path:
        if export_formats is None:
            typer.echo(f"Codex command: OK ({command_path}) {codex_version or ''}".rstrip())
    elif export_formats is None:
        typer.echo(f"Codex command: MISSING ({codex_command})", err=True)

    diagnostic_checks: list[DiagnosticCheck] = []
    if loaded:
        working_tree = _get_working_tree_status(loaded)
        diagnostic_checks = _collect_doctor_checks(loaded)
        if export_formats is None:
            _print_tracker_status(loaded)
            _print_workspace_status(loaded, working_tree)
            for check in diagnostic_checks:
                _print_diagnostic_check(check)
            _print_required_files(loaded)
            configure_logging(
                level=loaded.data.logging.level,
                json_logs=loaded.data.logging.json_logs,
                file_enabled=loaded.data.logging.file_enabled,
                log_dir=loaded.logs_dir,
            )
    else:
        working_tree = None

    exit_code = 0 if loaded and command_path else 1
    if loaded and working_tree and _workspace_doctor_has_error(loaded, working_tree):
        exit_code = 1
    if any(check.status == "ERROR" for check in diagnostic_checks):
        exit_code = 1

    if export_formats is not None:
        snapshot = _build_doctor_snapshot(
            repo_root=repo_root,
            loaded=loaded,
            config_error=config_error,
            codex_command=codex_command,
            command_path=command_path,
            codex_version=codex_version,
            codex_required=True,
            diagnostic_checks=diagnostic_checks,
            working_tree=working_tree,
            exit_code=exit_code,
        )
        output_path = _resolve_operator_report_output(
            repo_root=repo_root,
            loaded=loaded,
            output=output,
            default_name="doctor",
        )
        result = build_operator_report_exports(
            kind="doctor",
            snapshot=snapshot,
            output_path=output_path,
            formats=export_formats,
        )
        _print_operator_report_exports("Doctor", result.output_paths)
        typer.echo(
            "Doctor summary: "
            f"status={snapshot['summary']['overall_status']} "
            f"diagnostics={snapshot['summary']['diagnostic_count']} "
            f"exit_code={snapshot['summary']['exit_code']}"
        )
    raise typer.Exit(code=exit_code)


@app.command("run")
def run_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview work without external writes."),
    once: bool = typer.Option(
        False,
        "--once",
        help="Run a single polling cycle and exit.",
    ),
) -> None:
    loaded = _load_or_exit()
    _enforce_workspace_run_policy(loaded)
    configure_logging(
        level=loaded.data.logging.level,
        json_logs=loaded.data.logging.json_logs,
        file_enabled=loaded.data.logging.file_enabled,
        log_dir=loaded.logs_dir,
    )
    orchestrator = Orchestrator(loaded, dry_run=dry_run)
    if dry_run:
        previews = asyncio.run(orchestrator.run_once())
        if not previews:
            typer.echo("No runnable issues found for dry-run preview.")
            return
        for preview in previews:
            _print_dry_run_preview(preview)
        return

    if once:
        records = asyncio.run(orchestrator.run_once())
        if not records:
            typer.echo("No runnable issues found.")
            return
        for record in records:
            typer.echo(
                f"Issue #{record.issue_id}: status={record.status} attempts={record.attempts} summary={record.summary or '-'}"
            )
        return

    typer.echo("RepoAgents orchestrator started. Press Ctrl+C to stop.")
    try:
        asyncio.run(orchestrator.run_forever())
    except KeyboardInterrupt:
        typer.echo("RepoAgents orchestrator stopped.")


@app.command("trigger")
def trigger_command(
    issue_id: int,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview a single issue without external writes."),
    force: bool = typer.Option(False, "--force", help="Run even if the latest stored state would normally skip the issue."),
) -> None:
    loaded = _load_or_exit()
    _enforce_workspace_run_policy(loaded)
    configure_logging(
        level=loaded.data.logging.level,
        json_logs=loaded.data.logging.json_logs,
        file_enabled=loaded.data.logging.file_enabled,
        log_dir=loaded.logs_dir,
    )
    orchestrator = Orchestrator(loaded, dry_run=dry_run)
    try:
        result = asyncio.run(orchestrator.run_issue_by_id(issue_id, force=force))
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if result is None:
        _print_skipped_single_issue(orchestrator.state_store, issue_id)
        return

    if dry_run:
        _print_dry_run_preview(result)
        return

    typer.echo(f"Triggered issue #{issue_id}.")
    _print_run_record(result)


@app.command("webhook")
def webhook_command(
    event: str = typer.Option(..., "--event", help="GitHub webhook event name, for example issues or issue_comment."),
    payload: Path = typer.Option(
        ...,
        "--payload",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to a GitHub webhook JSON payload.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview the matched issue without external writes."),
    force: bool = typer.Option(False, "--force", help="Run even if the latest stored state would normally skip the issue."),
) -> None:
    loaded = _load_or_exit()
    _enforce_workspace_run_policy(loaded)
    configure_logging(
        level=loaded.data.logging.level,
        json_logs=loaded.data.logging.json_logs,
        file_enabled=loaded.data.logging.file_enabled,
        log_dir=loaded.logs_dir,
    )
    try:
        payload_body = load_webhook_payload(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(f"Could not load webhook payload from {payload}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    orchestrator = Orchestrator(loaded, dry_run=dry_run)
    decision, result = asyncio.run(
        orchestrator.handle_github_webhook(event=event, payload=payload_body, force=force)
    )
    typer.echo(
        "Webhook decision: "
        f"provider={decision.provider} event={decision.event} action={decision.action or '-'} "
        f"issue={decision.issue_id or '-'} should_run={decision.should_run}"
    )
    typer.echo(f"Reason: {decision.reason}")

    if not decision.should_run or decision.issue_id is None:
        return
    if result is None:
        _print_skipped_single_issue(orchestrator.state_store, decision.issue_id)
        return
    if dry_run:
        _print_dry_run_preview(result)
        return
    typer.echo(f"Triggered issue #{decision.issue_id} from webhook payload.")
    _print_run_record(result)


@app.command("status")
def status_command(
    issue: int | None = typer.Option(None, "--issue", help="Show a single issue run."),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text, json, markdown, or all.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional status report output path. Additional formats reuse the same filename stem.",
    ),
) -> None:
    try:
        loaded = load_config(resolve_repo_root(Path.cwd()))
    except ConfigLoadError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    store = RunStateStore(loaded.state_dir / "runs.json")
    all_records = store.all()
    if issue is not None:
        record = store.get(issue)
        if record is None:
            typer.echo(f"No run state recorded for issue #{issue}.", err=True)
            raise typer.Exit(code=1)
        records = [record]
    else:
        records = all_records

    output_format = format.strip().lower()
    export_formats: tuple[str, ...] | None = None
    if output_format != "text":
        try:
            export_formats = normalize_operator_report_formats((output_format,))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--format") from exc

    if not records and export_formats is None:
        typer.echo("No runs recorded yet.")
        return
    policy_alignment = _collect_report_policy_export_alignment(loaded)
    report_health_snapshot = build_report_health_snapshot(loaded=loaded)
    ops_snapshot = build_ops_snapshot_status_snapshot(loaded=loaded)
    policy_health = _collect_report_policy_health(
        loaded,
        policy_alignment=policy_alignment,
    )
    if export_formats is None:
        typer.echo(f"Run state: {loaded.state_dir / 'runs.json'}")
        if issue is None:
            counts = Counter(record.status.value for record in records)
            summary = ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
            typer.echo(f"Run summary: {summary}")
        _print_status_report_health(
            report_health_snapshot,
            policy_alignment=policy_alignment,
            policy_health=policy_health,
            ops_snapshot=ops_snapshot,
        )
        for record in records:
            _print_run_record(record)
        return

    snapshot = _build_status_snapshot(
        loaded=loaded,
        all_records=all_records,
        selected_records=records,
        issue_filter=issue,
        report_health_snapshot=report_health_snapshot,
        ops_snapshot=ops_snapshot,
        policy_alignment=policy_alignment,
        policy_health=policy_health,
    )
    output_path = _resolve_operator_report_output(
        repo_root=loaded.repo_root,
        loaded=loaded,
        output=output,
        default_name="status",
    )
    result = build_operator_report_exports(
        kind="status",
        snapshot=snapshot,
        output_path=output_path,
        formats=export_formats,
    )
    _print_operator_report_exports("Status", result.output_paths)
    typer.echo(
        "Status summary: "
        f"selected_runs={snapshot['summary']['selected_runs']} "
        f"total_runs={snapshot['summary']['total_runs']} "
        f"report_health={snapshot['report_health']['hero']['severity']}"
    )


@app.command("retry")
def retry_command(issue_id: int) -> None:
    loaded = _load_or_exit()
    store = RunStateStore(loaded.state_dir / "runs.json")
    record = store.get(issue_id)
    if record is None:
        typer.echo(f"No run state recorded for issue #{issue_id}.", err=True)
        raise typer.Exit(code=1)
    if record.status == RunLifecycle.IN_PROGRESS:
        typer.echo(
            f"Cannot force retry for issue #{issue_id} while a run is already in progress.",
            err=True,
        )
        raise typer.Exit(code=1)

    previous_status = record.status.value
    updated = store.force_retry(issue_id, "Manual retry requested from CLI.")
    typer.echo(
        f"Issue #{issue_id} scheduled for immediate retry at {updated.next_retry_at.isoformat()} "
        f"(previous_status={previous_status})."
    )


@app.command("clean")
def clean_command(
    issue: int | None = typer.Option(None, "--issue", help="Clean a single issue run."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview clean actions without deleting files."),
    sync_applied: bool = typer.Option(
        False,
        "--sync-applied",
        help="Include manifest-aware cleanup of applied sync archives.",
    ),
    sync_keep_groups: int | None = typer.Option(
        None,
        "--sync-keep-groups",
        min=1,
        max=500,
        help="Override cleanup.sync_applied_keep_groups_per_issue for this invocation.",
    ),
    report: bool = typer.Option(
        False,
        "--report",
        help="Write a cleanup report under .ai-repoagents/reports/.",
    ),
    report_format: str = typer.Option(
        "json",
        "--report-format",
        help="Cleanup report format: json, markdown, or all.",
    ),
    report_output: Path | None = typer.Option(
        None,
        "--report-output",
        help="Optional cleanup report output path.",
    ),
    show_remediation: bool = typer.Option(
        False,
        "--show-remediation",
        help="Print policy drift remediation guidance when linked sync audit exports were rendered under older thresholds.",
    ),
    show_mismatches: bool = typer.Option(
        False,
        "--show-mismatches",
        help="Print issue-filter mismatch warnings for linked sync audit exports.",
    ),
) -> None:
    loaded = _load_or_exit()
    store = RunStateStore(loaded.state_dir / "runs.json")
    records = store.all()
    if issue is not None:
        records = [record for record in records if record.issue_id == issue]
        if not records and not (sync_applied and _sync_applied_issue_exists(loaded, issue)):
            typer.echo(f"No run state recorded for issue #{issue}.", err=True)
            raise typer.Exit(code=1)

    resolved_sync_keep_groups = sync_keep_groups or loaded.data.cleanup.sync_applied_keep_groups_per_issue
    actions = _collect_clean_actions(
        loaded,
        records,
        issue_filter=issue,
        include_sync_applied=sync_applied,
        sync_keep_groups_per_issue=resolved_sync_keep_groups,
    )
    normalized_report_formats: tuple[str, ...] | None = None
    resolved_report_output = loaded.resolve(report_output) if report_output is not None else None
    if report:
        try:
            normalized_report_formats = normalize_cleanup_report_formats((report_format,))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--report-format") from exc
    if not actions:
        if report:
            report_result = build_cleanup_report(
                loaded,
                actions=[],
                dry_run=dry_run,
                include_sync_applied=sync_applied,
                issue_id=issue,
                sync_keep_groups_per_issue=resolved_sync_keep_groups if sync_applied else None,
                output_path=resolved_report_output,
                formats=normalized_report_formats or ("json",),
            )
            _print_cleanup_report_build_result_with_options(
                report_result,
                show_remediation=show_remediation,
                show_mismatches=show_mismatches,
            )
        typer.echo(
            "No stale local run data or applied sync archives to clean."
            if sync_applied
            else "No stale local run data to clean."
        )
        return

    if dry_run:
        typer.echo("Clean preview:")
        for action in actions:
            line = f"- {action.kind}: {action.path}"
            if action.detail:
                line += f" ({action.detail})"
            typer.echo(line)
        if report:
            report_result = build_cleanup_report(
                loaded,
                actions=actions,
                dry_run=True,
                include_sync_applied=sync_applied,
                issue_id=issue,
                sync_keep_groups_per_issue=resolved_sync_keep_groups if sync_applied else None,
                output_path=resolved_report_output,
                formats=normalized_report_formats or ("json",),
            )
            _print_cleanup_report_build_result_with_options(
                report_result,
                show_remediation=show_remediation,
                show_mismatches=show_mismatches,
            )
        return

    _execute_clean_actions(loaded, actions, store)
    typer.echo(f"Cleaned {len(actions)} stale local paths.")
    for action in actions:
        typer.echo(f"- {action.kind}: {action.path}")
    if report:
        report_result = build_cleanup_report(
            loaded,
            actions=actions,
            dry_run=False,
            include_sync_applied=sync_applied,
            issue_id=issue,
            sync_keep_groups_per_issue=resolved_sync_keep_groups if sync_applied else None,
            output_path=resolved_report_output,
            formats=normalized_report_formats or ("json",),
        )
        _print_cleanup_report_build_result_with_options(
            report_result,
            show_remediation=show_remediation,
            show_mismatches=show_mismatches,
        )


@app.command("dashboard")
def dashboard_command(
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Primary dashboard output path. Additional formats reuse the same filename stem.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        min=1,
        max=500,
        help="Maximum number of recent runs to include.",
    ),
    refresh_seconds: int = typer.Option(
        0,
        "--refresh-seconds",
        min=0,
        max=3600,
        help="Default browser auto-refresh interval embedded into the dashboard. 0 disables it.",
    ),
    format: list[str] | None = typer.Option(
        None,
        "--format",
        help="Repeat to export html, json, markdown, or all. Defaults to html.",
    ),
) -> None:
    loaded = _load_or_exit()
    output_path = loaded.resolve(output) if output is not None else None
    try:
        formats = normalize_dashboard_formats(format)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--format") from exc
    result = build_dashboard(
        loaded,
        output_path=output_path,
        limit=limit,
        refresh_seconds=refresh_seconds,
        formats=formats,
    )
    typer.echo("Dashboard exports:")
    for export_format, path in result.exported_paths.items():
        typer.echo(f"- {export_format}: {path}")
    typer.echo(f"Included {result.visible_runs} of {result.total_runs} recorded runs.")


@ops_app.command("snapshot")
def ops_snapshot_command(
    issue: int | None = typer.Option(None, "--issue", help="Filter status/sync audit to one issue id."),
    tracker: str | None = typer.Option(None, "--tracker", help="Filter sync audit to one tracker."),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Optional output directory for the bundle. Defaults to .ai-repoagents/reports/ops/<timestamp>/",
    ),
    dashboard_limit: int = typer.Option(
        50,
        "--dashboard-limit",
        min=1,
        max=500,
        help="Maximum number of runs to include in the dashboard snapshot.",
    ),
    sync_limit: int = typer.Option(
        50,
        "--sync-limit",
        min=1,
        max=500,
        help="Maximum number of sync entries to include in the sync audit snapshot.",
    ),
    refresh_seconds: int = typer.Option(
        0,
        "--refresh-seconds",
        min=0,
        max=3600,
        help="Default browser auto-refresh interval embedded into the bundled dashboard. 0 disables it.",
    ),
    include_cleanup_preview: bool = typer.Option(
        False,
        "--include-cleanup-preview",
        help="Generate a cleanup preview report inside the bundle.",
    ),
    include_cleanup_result: bool = typer.Option(
        False,
        "--include-cleanup-result",
        help="Copy the latest existing cleanup-result report into the bundle when present.",
    ),
    include_sync_check: bool = typer.Option(
        False,
        "--include-sync-check",
        help="Generate a dedicated sync manifest check report inside the bundle.",
    ),
    include_sync_repair_preview: bool = typer.Option(
        False,
        "--include-sync-repair-preview",
        help="Generate a dry-run sync manifest repair preview inside the bundle.",
    ),
    cleanup_sync_applied: bool = typer.Option(
        True,
        "--cleanup-sync-applied/--no-cleanup-sync-applied",
        help="Include manifest-aware sync archive retention when generating the bundled cleanup preview.",
    ),
    cleanup_keep_groups: int | None = typer.Option(
        None,
        "--cleanup-keep-groups",
        min=1,
        max=500,
        help="Override cleanup.sync_applied_keep_groups_per_issue for bundled cleanup preview generation.",
    ),
    archive: bool = typer.Option(
        False,
        "--archive",
        help="Pack the completed ops snapshot bundle into a tar.gz handoff archive.",
    ),
    archive_output: Path | None = typer.Option(
        None,
        "--archive-output",
        help="Optional archive output path. Defaults to a sibling <bundle>.tar.gz file.",
    ),
    history_limit: int | None = typer.Option(
        None,
        "--history-limit",
        min=1,
        max=500,
        help="Maximum number of ops snapshot history entries to retain in latest/history indices.",
    ),
    prune_history: bool = typer.Option(
        False,
        "--prune-history",
        help="Delete dropped managed bundle/archive paths recorded under .ai-repoagents/reports/ops/.",
    ),
) -> None:
    loaded = _load_or_exit()
    store = RunStateStore(loaded.state_dir / "runs.json")
    all_records = store.all()
    selected_records = all_records if issue is None else [record for record in all_records if record.issue_id == issue]

    policy_alignment = _collect_report_policy_export_alignment(loaded)
    policy_health = _collect_report_policy_health(
        loaded,
        policy_alignment=policy_alignment,
    )
    report_health_snapshot = build_report_health_snapshot(loaded=loaded)
    ops_snapshot = build_ops_snapshot_status_snapshot(loaded=loaded)
    working_tree = _get_working_tree_status(loaded)
    diagnostic_checks = _collect_doctor_checks(loaded)
    codex_command = loaded.data.codex.command
    command_path = shutil.which(codex_command)
    codex_version = _run_version([codex_command, "--version"]).strip() if command_path else None
    codex_required = _doctor_requires_codex_command(loaded)

    doctor_exit_code = 0 if command_path or not codex_required else 1
    if _workspace_doctor_has_error(loaded, working_tree):
        doctor_exit_code = 1
    if any(check.status == "ERROR" for check in diagnostic_checks):
        doctor_exit_code = 1

    bundle_root = loaded.resolve(output_dir) if output_dir is not None else default_ops_snapshot_bundle_dir(loaded.reports_dir)

    doctor_snapshot = _build_doctor_snapshot(
        repo_root=loaded.repo_root,
        loaded=loaded,
        config_error=None,
        codex_command=codex_command,
        command_path=command_path,
        codex_version=codex_version,
        codex_required=codex_required,
        diagnostic_checks=diagnostic_checks,
        working_tree=working_tree,
        exit_code=doctor_exit_code,
    )
    doctor_result = build_operator_report_exports(
        kind="doctor",
        snapshot=doctor_snapshot,
        output_path=bundle_root / "doctor.json",
        formats=("json", "markdown"),
    )

    status_snapshot = _build_status_snapshot(
        loaded=loaded,
        all_records=all_records,
        selected_records=selected_records,
        issue_filter=issue,
        report_health_snapshot=report_health_snapshot,
        ops_snapshot=ops_snapshot,
        policy_alignment=policy_alignment,
        policy_health=policy_health,
    )
    status_result = build_operator_report_exports(
        kind="status",
        snapshot=status_snapshot,
        output_path=bundle_root / "status.json",
        formats=("json", "markdown"),
    )
    sync_health_result, root_sync_health_paths, sync_health_component = (
        _build_ops_snapshot_sync_health_artifacts(
            loaded=loaded,
            bundle_root=bundle_root,
            records=selected_records,
            issue_filter=issue,
            tracker_filter=tracker,
            sync_limit=sync_limit,
            cleanup_sync_applied=cleanup_sync_applied,
            cleanup_keep_groups=cleanup_keep_groups,
        )
    )
    github_smoke_artifacts = _build_ops_snapshot_github_smoke_artifacts(
        loaded=loaded,
        bundle_root=bundle_root,
        issue_filter=issue,
        issue_limit=min(sync_limit, 10),
    )

    dashboard_result = build_dashboard(
        loaded,
        output_path=bundle_root / "dashboard.html",
        limit=dashboard_limit,
        refresh_seconds=refresh_seconds,
        formats=("html", "json", "markdown"),
    )
    sync_result = build_sync_audit_report(
        loaded,
        output_path=bundle_root / "sync-audit.json",
        formats=("json", "markdown"),
        issue_id=issue,
        tracker=tracker,
        limit=sync_limit,
    )
    bundle_ops_brief_result, root_ops_brief_result, ops_brief_component = (
        _build_ops_snapshot_ops_brief_artifacts(
            loaded=loaded,
            bundle_root=bundle_root,
            issue_filter=issue,
            tracker_filter=tracker,
            doctor_snapshot=doctor_snapshot,
            status_snapshot=status_snapshot,
            dashboard_snapshot=_load_report_json_payload(dashboard_result.exported_paths["json"]),
            sync_audit_snapshot=_load_report_json_payload(sync_result.output_paths["json"]),
            sync_health_snapshot=sync_health_result.snapshot,
            github_smoke_snapshot=github_smoke_artifacts[0].snapshot if github_smoke_artifacts else None,
        )
    )
    extra_components = _build_ops_snapshot_cleanup_components(
        loaded=loaded,
        bundle_root=bundle_root,
        records=selected_records,
        issue_filter=issue,
        include_cleanup_preview=include_cleanup_preview,
        include_cleanup_result=include_cleanup_result,
        cleanup_sync_applied=cleanup_sync_applied,
        cleanup_keep_groups=cleanup_keep_groups,
    )
    extra_components.update(
        _build_ops_snapshot_sync_components(
            loaded=loaded,
            bundle_root=bundle_root,
            issue_filter=issue,
            tracker_filter=tracker,
            include_sync_check=include_sync_check,
            include_sync_repair_preview=include_sync_repair_preview,
        )
    )
    extra_components["sync_health"] = sync_health_component
    if github_smoke_artifacts is not None:
        _, _, github_smoke_component = github_smoke_artifacts
        extra_components["github_smoke"] = github_smoke_component
    extra_components["ops_brief"] = ops_brief_component
    bundle_result = build_ops_snapshot_bundle(
        bundle_dir=bundle_root,
        repo_root=loaded.repo_root,
        config_path=loaded.config_path,
        issue_filter=issue,
        tracker_filter=tracker,
        dashboard_limit=dashboard_limit,
        sync_limit=sync_limit,
        refresh_seconds=refresh_seconds,
        doctor_snapshot=doctor_snapshot,
        doctor_result=doctor_result,
        status_snapshot=status_snapshot,
        status_result=status_result,
        dashboard_result=dashboard_result,
        sync_result=sync_result,
        extra_components=extra_components,
    )
    effective_history_limit = history_limit or loaded.data.cleanup.ops_snapshot_keep_entries
    provisional_index_result = build_ops_snapshot_index(
        ops_root=loaded.reports_dir / "ops",
        bundle_result=bundle_result,
        archive_result=None,
        history_limit=effective_history_limit,
    )
    provisional_ops_status_snapshot = build_ops_status_snapshot(
        loaded=loaded,
        history_preview_limit=min(provisional_index_result.history_limit, 10),
    )
    _, _, ops_status_component = _build_ops_snapshot_ops_status_artifacts(
        loaded=loaded,
        bundle_root=bundle_root,
        snapshot=provisional_ops_status_snapshot,
    )
    extra_components["ops_status"] = ops_status_component
    bundle_result = build_ops_snapshot_bundle(
        bundle_dir=bundle_root,
        repo_root=loaded.repo_root,
        config_path=loaded.config_path,
        issue_filter=issue,
        tracker_filter=tracker,
        dashboard_limit=dashboard_limit,
        sync_limit=sync_limit,
        refresh_seconds=refresh_seconds,
        doctor_snapshot=doctor_snapshot,
        doctor_result=doctor_result,
        status_snapshot=status_snapshot,
        status_result=status_result,
        dashboard_result=dashboard_result,
        sync_result=sync_result,
        extra_components=extra_components,
    )
    archive_result = None
    if archive:
        archive_result = build_ops_snapshot_archive(
            bundle_dir=bundle_result.bundle_dir,
            output_path=loaded.resolve(archive_output) if archive_output is not None else None,
        )
    index_result = build_ops_snapshot_index(
        ops_root=loaded.reports_dir / "ops",
        bundle_result=bundle_result,
        archive_result=archive_result,
        history_limit=effective_history_limit,
        additional_dropped_entries=provisional_index_result.dropped_entries,
    )
    effective_prune_history = prune_history or loaded.data.cleanup.ops_snapshot_prune_managed
    prune_result = None
    if effective_prune_history and index_result.dropped_entries:
        prune_result = prune_ops_snapshot_history(
            ops_root=loaded.reports_dir / "ops",
            dropped_entries=index_result.dropped_entries,
        )
    ops_status_snapshot = build_ops_status_snapshot(
        loaded=loaded,
        history_preview_limit=min(index_result.history_limit, 10),
    )
    _, root_ops_status_result, _ = _build_ops_snapshot_ops_status_artifacts(
        loaded=loaded,
        bundle_root=bundle_root,
        snapshot=ops_status_snapshot,
    )

    typer.echo("Ops snapshot bundle:")
    typer.echo(f"- bundle_dir: {bundle_result.bundle_dir}")
    for name, path in sorted(bundle_result.output_paths.items()):
        typer.echo(f"- {name}: {path}")
    if archive_result is not None:
        typer.echo(f"- archive_path: {archive_result.archive_path}")
        typer.echo(f"- archive_sha256: {archive_result.sha256}")
        typer.echo(f"- archive_size_bytes: {archive_result.size_bytes}")
        typer.echo(f"- archive_file_count: {archive_result.file_count}")
        typer.echo(f"- archive_member_count: {archive_result.member_count}")
    typer.echo(f"- latest_index_json: {index_result.latest_json}")
    typer.echo(f"- latest_index_markdown: {index_result.latest_markdown}")
    typer.echo(f"- history_index_json: {index_result.history_json}")
    typer.echo(f"- history_index_markdown: {index_result.history_markdown}")
    typer.echo(f"- bundle_ops_brief_json: {bundle_ops_brief_result.output_paths['json']}")
    typer.echo(f"- bundle_ops_brief_markdown: {bundle_ops_brief_result.output_paths['markdown']}")
    typer.echo(f"- root_ops_brief_json: {root_ops_brief_result.output_paths['json']}")
    typer.echo(f"- root_ops_brief_markdown: {root_ops_brief_result.output_paths['markdown']}")
    typer.echo(f"- bundle_sync_health_json: {sync_health_result.output_paths['json']}")
    typer.echo(f"- bundle_sync_health_markdown: {sync_health_result.output_paths['markdown']}")
    typer.echo(f"- root_sync_health_json: {root_sync_health_paths['json']}")
    typer.echo(f"- root_sync_health_markdown: {root_sync_health_paths['markdown']}")
    if github_smoke_artifacts is not None:
        bundle_github_smoke_result, root_github_smoke_result, _ = github_smoke_artifacts
        typer.echo(f"- bundle_github_smoke_json: {bundle_github_smoke_result.output_paths['json']}")
        typer.echo(f"- bundle_github_smoke_markdown: {bundle_github_smoke_result.output_paths['markdown']}")
        typer.echo(f"- root_github_smoke_json: {root_github_smoke_result.output_paths['json']}")
        typer.echo(f"- root_github_smoke_markdown: {root_github_smoke_result.output_paths['markdown']}")
    typer.echo(f"- root_ops_status_json: {root_ops_status_result.output_paths['json']}")
    typer.echo(f"- root_ops_status_markdown: {root_ops_status_result.output_paths['markdown']}")
    typer.echo(f"- history_limit: {index_result.history_limit}")
    typer.echo(f"- history_entry_count: {index_result.entry_count}")
    typer.echo(f"- dropped_history_entries: {len(index_result.dropped_entries)}")
    if effective_prune_history:
        typer.echo(f"- prune_history: {str(True).lower()}")
        typer.echo(f"- pruned_bundle_dirs: {len(prune_result.removed_bundle_dirs) if prune_result else 0}")
        typer.echo(f"- pruned_archives: {len(prune_result.removed_archives) if prune_result else 0}")
        typer.echo(f"- skipped_external_paths: {prune_result.skipped_external_paths if prune_result else 0}")
        typer.echo(f"- skipped_active_paths: {prune_result.skipped_active_paths if prune_result else 0}")
        typer.echo(f"- missing_pruned_paths: {prune_result.missing_paths if prune_result else 0}")
    elif index_result.dropped_entries:
        typer.echo("- history_prune_note: dropped entries remain on disk until you re-run with --prune-history.")
    typer.echo(f"- overall_status: {bundle_result.overall_status}")
    for name, status in bundle_result.component_statuses.items():
        typer.echo(f"- {name}: {status}")

    if bundle_result.overall_status == "issues":
        raise typer.Exit(code=1)


@ops_app.command("status")
def ops_status_command(
    limit: int = typer.Option(
        10,
        "--limit",
        min=1,
        max=100,
        help="Maximum number of recent ops history entries to include.",
    ),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text, json, markdown, or all.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional ops status output path. Additional formats reuse the same filename stem.",
    ),
) -> None:
    loaded = _load_or_exit()
    output_format = format.strip().lower()
    export_formats: tuple[str, ...] | None = None
    if output_format != "text":
        try:
            export_formats = normalize_ops_status_formats((output_format,))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--format") from exc

    snapshot = build_ops_status_snapshot(
        loaded=loaded,
        history_preview_limit=limit,
    )
    if export_formats is None:
        typer.echo(render_ops_status_text(snapshot), nl=False)
        return

    output_path = _resolve_operator_report_output(
        repo_root=loaded.repo_root,
        loaded=loaded,
        output=output,
        default_name="ops-status",
    )
    result = build_ops_status_exports(
        snapshot=snapshot,
        output_path=output_path,
        formats=export_formats,
    )
    _print_operator_report_exports("Ops status", result.output_paths)
    typer.echo(
        "Ops status summary: "
        f"status={snapshot['summary']['status']} "
        f"index={snapshot['summary']['index_status']} "
        f"latest_bundle={snapshot['summary']['latest_bundle_status']}"
    )


@github_app.command("smoke")
def github_smoke_command(
    issue: int | None = typer.Option(
        None,
        "--issue",
        help="Optional issue id to fetch in addition to listing open issues.",
    ),
    limit: int = typer.Option(
        5,
        "--limit",
        min=1,
        max=50,
        help="Maximum number of open issues to include in the sampled issue list.",
    ),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text, json, markdown, or all.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional GitHub smoke output path. Additional formats reuse the same filename stem.",
    ),
    require_write_ready: bool = typer.Option(
        False,
        "--require-write-ready",
        help="Exit non-zero when live publish preflight is not ready.",
    ),
) -> None:
    loaded = _load_or_exit()
    if loaded.data.tracker.kind.value != "github":
        typer.echo("GitHub smoke is only available when tracker.kind=github.", err=True)
        raise typer.Exit(code=1)
    if loaded.data.tracker.mode.value == "fixture":
        typer.echo("GitHub smoke requires tracker.mode=rest.", err=True)
        raise typer.Exit(code=1)

    output_format = format.strip().lower()
    export_formats: tuple[str, ...] | None = None
    if output_format != "text":
        try:
            export_formats = normalize_github_smoke_formats((output_format,))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--format") from exc

    tracker = build_tracker(loaded, dry_run=False)
    try:
        snapshot = asyncio.run(
            build_github_smoke_snapshot(
                loaded=loaded,
                tracker=tracker,
                issue_id=issue,
                issue_limit=limit,
            )
        )
    finally:
        asyncio.run(tracker.aclose())

    if export_formats is None:
        typer.echo(render_github_smoke_text(snapshot), nl=False)
    else:
        output_path = _resolve_operator_report_output(
            repo_root=loaded.repo_root,
            loaded=loaded,
            output=output,
            default_name="github-smoke",
        )
        result = build_github_smoke_exports(
            snapshot=snapshot,
            output_path=output_path,
            formats=export_formats,
        )
        typer.echo("GitHub smoke exports:")
        for export_format, path in result.output_paths.items():
            typer.echo(f"- {export_format}: {path}")
        summary = snapshot.get("summary")
        if not isinstance(summary, dict):
            summary = {}
        typer.echo(
            "GitHub smoke summary: "
            f"status={summary.get('status', 'unknown')} "
            f"open_issues={summary.get('open_issue_count', 0)} "
            f"sampled_issue={summary.get('sampled_issue_id')}"
        )

    summary = snapshot.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    if summary.get("status") == "issues":
        raise typer.Exit(code=1)
    publish = snapshot.get("publish")
    if (
        require_write_ready
        and isinstance(publish, dict)
        and publish.get("status") == "warn"
    ):
        raise typer.Exit(code=1)


@sync_app.command("ls")
def sync_list_command(
    issue: int | None = typer.Option(None, "--issue", help="Filter staged artifacts to one issue id."),
    tracker: str | None = typer.Option(None, "--tracker", help="Filter by staged tracker name, for example local-markdown."),
    action: str | None = typer.Option(None, "--action", help="Filter by staged action, for example comment or pr-body."),
    scope: str = typer.Option("pending", "--scope", help="Inventory scope: pending, applied, or all."),
    format: str = typer.Option("text", "--format", help="Output format: text or json."),
) -> None:
    loaded = _load_or_exit()
    output_format = format.strip().lower()
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("Unsupported sync format. Expected one of: text, json", param_hint="--format")

    artifacts = list_sync_artifacts(loaded, issue_id=issue, tracker=tracker, action=action, scope=scope)
    if output_format == "json":
        typer.echo(
            json.dumps(
                [
                    {
                        "state": artifact.state,
                        "tracker": artifact.tracker,
                        "issue_id": artifact.issue_id,
                        "action": artifact.action,
                        "format": artifact.format,
                        "staged_at": artifact.staged_at,
                        "relative_path": artifact.relative_path,
                        "path": str(artifact.path),
                        "summary": artifact.summary,
                        "metadata": artifact.metadata,
                        "normalized": artifact.normalized,
                    }
                    for artifact in artifacts
                ],
                indent=2,
                sort_keys=True,
            )
        )
        return

    if not artifacts:
        typer.echo("No staged sync artifacts found.")
        return

    typer.echo(f"Sync scope: {scope}")
    typer.echo(f"Pending root: {loaded.sync_dir}")
    typer.echo(f"Applied root: {loaded.sync_applied_dir}")
    typer.echo(f"Artifacts: {len(artifacts)}")
    for artifact in artifacts:
        typer.echo(
            f"- state={artifact.state} tracker={artifact.tracker} issue={artifact.issue_id or '-'} action={artifact.action} "
            f"format={artifact.format} staged_at={artifact.staged_at or '-'} path={artifact.relative_path}"
        )
        if artifact.summary:
            typer.echo(f"  summary: {artifact.summary}")


@sync_app.command("show")
def sync_show_command(
    artifact: str = typer.Argument(..., help="Relative path under .ai-repoagents/sync, basename, or absolute path."),
    scope: str = typer.Option("all", "--scope", help="Lookup scope: pending, applied, or all."),
    raw: bool = typer.Option(False, "--raw", help="Print raw file contents instead of the parsed view."),
) -> None:
    loaded = _load_or_exit()
    try:
        staged = resolve_sync_artifact(loaded, artifact, scope=scope)
    except SyncArtifactLookupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if raw:
        typer.echo(staged.path.read_text(encoding="utf-8"))
        return

    typer.echo(f"Path: {staged.path}")
    typer.echo(f"Relative path: {staged.relative_path}")
    typer.echo(f"State: {staged.state}")
    typer.echo(f"Tracker: {staged.tracker}")
    typer.echo(f"Issue: {staged.issue_id or '-'}")
    typer.echo(f"Action: {staged.action}")
    typer.echo(f"Format: {staged.format}")
    typer.echo(f"Staged at: {staged.staged_at or '-'}")
    if staged.summary:
        typer.echo(f"Summary: {staged.summary}")
    if staged.metadata:
        typer.echo("Metadata:")
        typer.echo(_indent_block(yaml.safe_dump(staged.metadata, sort_keys=False).strip(), prefix="  "))
    if staged.normalized:
        typer.echo("Normalized:")
        typer.echo(_indent_block(yaml.safe_dump(staged.normalized, sort_keys=False).strip(), prefix="  "))
    if staged.body:
        typer.echo("Body:")
        typer.echo(_indent_block(staged.body, prefix="  "))


@sync_app.command("apply")
def sync_apply_command(
    artifact: str | None = typer.Argument(
        None,
        help="Relative path under .ai-repoagents/sync, basename, or absolute path. Optional when using filters with --latest.",
    ),
    issue: int | None = typer.Option(None, "--issue", help="Filter apply selection to one issue id."),
    tracker: str | None = typer.Option(None, "--tracker", help="Filter by tracker, for example local-markdown."),
    action: str | None = typer.Option(None, "--action", help="Filter by action, for example comment or labels."),
    latest: bool = typer.Option(False, "--latest", help="Apply the newest artifact that matches the filters."),
    bundle: bool = typer.Option(False, "--bundle", help="Apply the related branch/pr/pr-body handoff bundle when available."),
    keep_source: bool = typer.Option(False, "--keep-source", help="Copy into the applied archive without removing the pending source artifact."),
) -> None:
    loaded = _load_or_exit()
    try:
        selected = _resolve_sync_selection(
            loaded,
            artifact=artifact,
            issue=issue,
            tracker=tracker,
            action=action,
            latest=latest,
        )
        if bundle:
            results = apply_sync_bundle(loaded, selected, keep_source=keep_source)
        else:
            results = [apply_sync_artifact(loaded, selected, keep_source=keep_source)]
    except SyncArtifactLookupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if bundle:
        typer.echo("Applied sync bundle:")
        typer.echo(f"- tracker: {results[0].tracker}")
        typer.echo(f"- issue: {results[0].issue_id or '-'}")
        typer.echo(f"- artifacts: {len(results)}")
        for result in results:
            typer.echo(f"- action: {result.action}")
            typer.echo(f"  effect: {result.effect}")
            typer.echo(f"  archived_path: {result.archived_path}")
            typer.echo(f"  manifest_path: {result.manifest_path}")
            if keep_source:
                typer.echo(f"  source_path: {result.source_path} (retained)")
            else:
                typer.echo(f"  source_path: {result.source_path} (moved)")
        return

    result = results[0]
    typer.echo("Applied sync artifact:")
    typer.echo(f"- tracker: {result.tracker}")
    typer.echo(f"- issue: {result.issue_id or '-'}")
    typer.echo(f"- action: {result.action}")
    typer.echo(f"- effect: {result.effect}")
    typer.echo(f"- archived_path: {result.archived_path}")
    typer.echo(f"- manifest_path: {result.manifest_path}")
    if keep_source:
        typer.echo(f"- source_path: {result.source_path} (retained)")
    else:
        typer.echo(f"- source_path: {result.source_path} (moved)")


@sync_app.command("check")
def sync_check_command(
    issue: int | None = typer.Option(None, "--issue", help="Inspect one applied sync issue id."),
    tracker: str | None = typer.Option(None, "--tracker", help="Filter by tracker, for example local-file."),
    format: str = typer.Option("text", "--format", help="Output format: text or json."),
) -> None:
    loaded = _load_or_exit()
    output_format = format.strip().lower()
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("Unsupported sync format. Expected one of: text, json", param_hint="--format")
    reports = inspect_applied_sync_manifests(loaded, issue_id=issue, tracker=tracker)
    if output_format == "json":
        typer.echo(
            json.dumps(
                [
                    serialize_sync_manifest_report(report, include_issue_root=True)
                    for report in reports
                ],
                indent=2,
                sort_keys=True,
            )
        )
        if any(report.findings for report in reports):
            raise typer.Exit(code=1)
        return
    if not reports:
        typer.echo("No applied sync manifests found.")
        return
    typer.echo("Applied sync manifest check:")
    for report in reports:
        status = "issues" if report.findings else "ok"
        typer.echo(
            f"- tracker={report.tracker} issue={report.issue_id or '-'} status={status} "
            f"entries={report.manifest_entry_count} archives={len(report.archive_files)} findings={len(report.findings)}"
        )
        if report.findings:
            for finding in report.findings:
                suffix = f" path={finding.path}" if finding.path else ""
                entry_key = f" entry_key={finding.entry_key}" if finding.entry_key else ""
                typer.echo(f"  - {finding.code}:{entry_key}{suffix} {finding.message}")
    if any(report.findings for report in reports):
        raise typer.Exit(code=1)


@sync_app.command("repair")
def sync_repair_command(
    issue: int | None = typer.Option(None, "--issue", help="Repair one applied sync issue id."),
    tracker: str | None = typer.Option(None, "--tracker", help="Filter by tracker, for example local-file."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview manifest repairs without writing files."),
    format: str = typer.Option("text", "--format", help="Output format: text or json."),
) -> None:
    loaded = _load_or_exit()
    output_format = format.strip().lower()
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("Unsupported sync format. Expected one of: text, json", param_hint="--format")
    results = repair_applied_sync_manifests(loaded, issue_id=issue, tracker=tracker, dry_run=dry_run)
    if output_format == "json":
        typer.echo(
            json.dumps(
                [
                    serialize_sync_manifest_repair_result(result, include_issue_root=True)
                    for result in results
                ],
                indent=2,
                sort_keys=True,
            )
        )
    else:
        if not results:
            typer.echo("No applied sync manifests found.")
            return
        typer.echo("Applied sync manifest repair preview:" if dry_run else "Applied sync manifest repair:")
        for result in results:
            status = "changed" if result.changed else "unchanged"
            typer.echo(
                f"- tracker={result.tracker} issue={result.issue_id or '-'} status={status} "
                f"entries={result.manifest_entry_count_before}->{result.manifest_entry_count_after} "
                f"findings={result.findings_before}->{result.findings_after}"
            )
            typer.echo(
                f"  dropped_entries={result.dropped_entries} adopted_archives={result.adopted_archives} "
                f"normalized_entries={result.normalized_entries} manifest={result.manifest_path}"
            )
    if any(result.findings_after for result in results):
        raise typer.Exit(code=1)


@sync_app.command("audit")
def sync_audit_command(
    issue: int | None = typer.Option(None, "--issue", help="Audit one issue id across pending and applied sync state."),
    tracker: str | None = typer.Option(None, "--tracker", help="Filter by tracker, for example local-markdown."),
    format: str = typer.Option(
        "all",
        "--format",
        help="Export format: json, markdown, or all.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional export path. Defaults to .ai-repoagents/reports/sync-audit.<ext>.",
    ),
    limit: int = typer.Option(50, "--limit", min=1, max=500, help="Limit included pending entries and retention entries."),
    show_remediation: bool = typer.Option(
        False,
        "--show-remediation",
        help="Print policy drift remediation guidance when linked cleanup reports were rendered under older thresholds.",
    ),
    show_mismatches: bool = typer.Option(
        False,
        "--show-mismatches",
        help="Print issue-filter mismatch warnings for linked cleanup reports.",
    ),
) -> None:
    loaded = _load_or_exit()
    try:
        normalized_formats = normalize_sync_audit_formats((format,))
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--format") from exc

    result = build_sync_audit_report(
        loaded,
        output_path=output,
        formats=normalized_formats,
        issue_id=issue,
        tracker=tracker,
        limit=limit,
    )
    typer.echo("Sync audit exports:")
    for export_format, export_path in result.output_paths.items():
        typer.echo(f"- {export_format}: {export_path}")
    typer.echo(
        f"Overall status: {result.overall_status} "
        f"(pending={result.pending_artifacts}, integrity_issues={result.integrity_issue_count}, prunable_groups={result.prunable_groups})"
    )
    if result.related_cleanup_reports:
        typer.echo(f"Linked cleanup reports: {result.related_cleanup_reports}")
    if result.cleanup_report_mismatches:
        typer.echo(f"Cleanup report mismatches: {result.cleanup_report_mismatches}")
    if result.related_cleanup_policy_drifts:
        typer.echo(f"Cleanup report policy drifts: {result.related_cleanup_policy_drifts}")
    _print_related_report_details_block(
        title="Related cleanup report details:",
        mismatch_warnings=result.cleanup_mismatch_warnings,
        policy_drift_warnings=result.cleanup_policy_drift_warnings,
        remediation=result.policy_drift_guidance,
        show_mismatches=show_mismatches,
        show_remediation=show_remediation,
    )
    if result.overall_status == "issues":
        raise typer.Exit(code=1)


@sync_app.command("health")
def sync_health_command(
    issue: int | None = typer.Option(None, "--issue", help="Inspect one issue id across the sync pipeline."),
    tracker: str | None = typer.Option(None, "--tracker", help="Filter by tracker, for example local-markdown."),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text, json, markdown, or all.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional export path. Defaults to .ai-repoagents/reports/sync-health.<ext>.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        min=1,
        max=500,
        help="Maximum number of sync entries to include in the audit portion of the snapshot.",
    ),
    cleanup_sync_applied: bool = typer.Option(
        True,
        "--cleanup-sync-applied/--no-cleanup-sync-applied",
        help="Include manifest-aware sync archive retention when building the cleanup preview.",
    ),
    cleanup_keep_groups: int | None = typer.Option(
        None,
        "--cleanup-keep-groups",
        min=1,
        max=500,
        help="Override cleanup.sync_applied_keep_groups_per_issue for the bundled cleanup preview.",
    ),
    show_remediation: bool = typer.Option(
        False,
        "--show-remediation",
        help="Print policy drift remediation guidance for linked cleanup/sync audit reports.",
    ),
    show_mismatches: bool = typer.Option(
        False,
        "--show-mismatches",
        help="Print issue-filter mismatch warnings for linked cleanup/sync audit reports.",
    ),
) -> None:
    loaded = _load_or_exit()
    output_format = format.strip().lower()
    if output_format not in {"text", "json", "markdown", "all"}:
        raise typer.BadParameter(
            "Unsupported sync health format. Expected one of: text, json, markdown, all",
            param_hint="--format",
        )
    resolved_keep_groups = cleanup_keep_groups or loaded.data.cleanup.sync_applied_keep_groups_per_issue
    store = RunStateStore(loaded.state_dir / "runs.json")
    records = store.all()
    if issue is not None:
        records = [record for record in records if record.issue_id == issue]
    cleanup_actions = _collect_clean_actions(
        loaded,
        records,
        issue_filter=issue,
        include_sync_applied=cleanup_sync_applied,
        sync_keep_groups_per_issue=resolved_keep_groups,
    )
    if output_format == "text":
        snapshot = build_sync_health_snapshot(
            loaded,
            cleanup_actions=cleanup_actions,
            issue_id=issue,
            tracker=tracker,
            limit=limit,
            cleanup_include_sync_applied=cleanup_sync_applied,
            cleanup_keep_groups_per_issue=resolved_keep_groups if cleanup_sync_applied else None,
        )
        typer.echo(render_sync_health_text(snapshot))
        _print_sync_health_related_report_details(
            snapshot,
            show_remediation=show_remediation,
            show_mismatches=show_mismatches,
        )
        summary = snapshot.get("summary")
        if isinstance(summary, dict) and summary.get("overall_status") == "issues":
            raise typer.Exit(code=1)
        return

    try:
        normalized_formats = normalize_sync_health_formats((output_format,))
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--format") from exc

    result = build_sync_health_report(
        loaded,
        cleanup_actions=cleanup_actions,
        issue_id=issue,
        tracker=tracker,
        limit=limit,
        cleanup_include_sync_applied=cleanup_sync_applied,
        cleanup_keep_groups_per_issue=resolved_keep_groups if cleanup_sync_applied else None,
        output_path=loaded.resolve(output) if output is not None else None,
        formats=normalized_formats,
    )
    typer.echo("Sync health exports:")
    for export_format, path in result.output_paths.items():
        typer.echo(f"- {export_format}: {path}")
    typer.echo(
        "Sync health summary: "
        f"status={result.overall_status} "
        f"pending={result.pending_artifacts} "
        f"integrity_issues={result.integrity_issue_count} "
        f"repair_changed={result.repair_changed_reports} "
        f"cleanup_actions={result.cleanup_action_count}"
    )
    if result.next_actions:
        typer.echo("Next actions:")
        for action in result.next_actions:
            typer.echo(f"- {action}")
    _print_sync_health_build_result_with_options(
        result,
        show_remediation=show_remediation,
        show_mismatches=show_mismatches,
    )
    if result.overall_status == "issues":
        raise typer.Exit(code=1)


@release_app.command("preview")
def release_preview_command(
    version: str | None = typer.Option(
        None,
        "--version",
        help="Optional target release version. Defaults to the inferred next preview version.",
    ),
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="Optional target git tag. Defaults to v<version>.",
    ),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text, json, markdown, or all.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional export path. Defaults to .ai-repoagents/reports/release-preview.<ext>.",
    ),
) -> None:
    repo_root = resolve_repo_root()
    try:
        loaded = load_config(repo_root)
    except ConfigLoadError:
        loaded = None
    output_format = format.strip().lower()
    export_formats: tuple[str, ...] | None = None
    if output_format != "text":
        try:
            export_formats = normalize_release_preview_formats((output_format,))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--format") from exc

    snapshot = build_release_preview_snapshot(
        loaded=loaded,
        repo_root=repo_root,
        target_version=version,
        target_tag=tag,
    )
    if export_formats is None:
        typer.echo(render_release_preview_text(snapshot), nl=False)
        if snapshot["summary"]["status"] == "issues":
            raise typer.Exit(code=1)
        return

    output_path = _resolve_operator_report_output(
        repo_root=repo_root,
        loaded=loaded,
        output=output,
        default_name="release-preview",
    )
    result = build_release_preview_exports(
        snapshot=snapshot,
        output_path=output_path,
        formats=export_formats,
    )
    _print_operator_report_exports("Release preview", result.output_paths)
    typer.echo(f"- notes_markdown: {result.notes_markdown_path}")
    typer.echo(
        "Release preview summary: "
        f"status={result.snapshot['summary']['status']} "
        f"target={result.snapshot['target']['tag']} "
        f"warnings={result.snapshot['summary']['warning_count']} "
        f"errors={result.snapshot['summary']['error_count']}"
    )
    if result.snapshot["summary"]["status"] == "issues":
        raise typer.Exit(code=1)


@release_app.command("announce")
def release_announce_command(
    version: str | None = typer.Option(
        None,
        "--version",
        help="Optional target release version. Defaults to the inferred next preview version.",
    ),
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="Optional target git tag. Defaults to v<version>.",
    ),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text, json, markdown, or all.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional export path. Defaults to .ai-repoagents/reports/release-announce.<ext>.",
    ),
) -> None:
    repo_root = resolve_repo_root()
    try:
        loaded = load_config(repo_root)
    except ConfigLoadError:
        loaded = None
    output_format = format.strip().lower()
    export_formats: tuple[str, ...] | None = None
    if output_format != "text":
        try:
            export_formats = normalize_release_announcement_formats((output_format,))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--format") from exc

    snapshot = build_release_announcement_snapshot(
        loaded=loaded,
        repo_root=repo_root,
        target_version=version,
        target_tag=tag,
    )
    if export_formats is None:
        typer.echo(render_release_announcement_text(snapshot), nl=False)
        if snapshot["preview"]["status"] == "issues":
            raise typer.Exit(code=1)
        return

    output_path = _resolve_operator_report_output(
        repo_root=repo_root,
        loaded=loaded,
        output=output,
        default_name="release-announce",
    )
    result = build_release_announcement_exports(
        snapshot=snapshot,
        output_path=output_path,
        formats=export_formats,
    )
    _print_operator_report_exports("Release announcement", result.output_paths)
    for key, path in sorted(result.snippet_paths.items()):
        typer.echo(f"- {key}: {path}")
    typer.echo(
        "Release announcement summary: "
        f"status={result.snapshot['summary']['status']} "
        f"target={result.snapshot['target']['tag']} "
        f"preview_status={result.snapshot['preview']['status']} "
        f"snippets={result.snapshot['summary']['snippet_count']}"
    )
    if result.snapshot["preview"]["status"] == "issues":
        raise typer.Exit(code=1)


@release_app.command("check")
def release_check_command(
    version: str | None = typer.Option(
        None,
        "--version",
        help="Optional target release version. Defaults to the inferred next preview version.",
    ),
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="Optional target git tag. Defaults to v<version>.",
    ),
    format: str = typer.Option(
        "all",
        "--format",
        help="Output format: text, json, markdown, or all.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional export path. Defaults to .ai-repoagents/reports/release-checklist.<ext>.",
    ),
    run_tests: bool = typer.Option(
        True,
        "--run-tests/--no-run-tests",
        help="Run `uv run pytest -q` as part of the preflight gate.",
    ),
    build: bool = typer.Option(
        True,
        "--build/--no-build",
        help="Run `uv build` before validating release assets.",
    ),
    smoke_install: bool = typer.Option(
        True,
        "--smoke-install/--no-smoke-install",
        help="Install the built wheel into a temporary venv and run `repoagents --help`.",
    ),
) -> None:
    repo_root = resolve_repo_root()
    try:
        loaded = load_config(repo_root)
    except ConfigLoadError:
        loaded = None
    output_format = format.strip().lower()
    export_formats: tuple[str, ...] | None = None
    if output_format != "text":
        try:
            export_formats = normalize_release_checklist_formats((output_format,))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--format") from exc

    snapshot = build_release_checklist_snapshot(
        loaded=loaded,
        repo_root=repo_root,
        target_version=version,
        target_tag=tag,
        run_tests=run_tests,
        build=build,
        smoke_install=smoke_install,
    )
    if export_formats is None:
        typer.echo(render_release_checklist_text(snapshot), nl=False)
        if snapshot["summary"]["status"] != "clean":
            raise typer.Exit(code=1)
        return

    output_path = _resolve_operator_report_output(
        repo_root=repo_root,
        loaded=loaded,
        output=output,
        default_name="release-checklist",
    )
    result = build_release_checklist_exports(
        snapshot=snapshot,
        output_path=output_path,
        formats=export_formats,
    )
    _print_operator_report_exports("Release checklist", result.output_paths)
    artifacts = result.snapshot["artifacts"]
    typer.echo(
        f"- release_preview_notes: {artifacts['preview']['notes_markdown_path']}"
    )
    typer.echo(
        f"- release_asset_summary: {artifacts['assets']['asset_summary_path']}"
    )
    typer.echo(
        "Release checklist summary: "
        f"status={result.snapshot['summary']['status']} "
        f"ready={result.snapshot['summary']['ready_to_publish']} "
        f"target={result.snapshot['target']['tag']} "
        f"errors={result.snapshot['summary']['error_count']} "
        f"warnings={result.snapshot['summary']['warning_count']}"
    )
    if result.snapshot["summary"]["status"] != "clean":
        raise typer.Exit(code=1)


@release_app.command("assets")
def release_assets_command(
    version: str | None = typer.Option(
        None,
        "--version",
        help="Optional target release version. Defaults to the inferred next preview version.",
    ),
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="Optional target git tag. Defaults to v<version>.",
    ),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output format: text, json, markdown, or all.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional export path. Defaults to .ai-repoagents/reports/release-assets.<ext>.",
    ),
    build: bool = typer.Option(
        False,
        "--build",
        help="Run `uv build` before collecting dist artifact metadata.",
    ),
    smoke_install: bool = typer.Option(
        False,
        "--smoke-install",
        help="Create a temporary venv, install the built wheel, and run `repoagents --help`.",
    ),
) -> None:
    repo_root = resolve_repo_root()
    try:
        loaded = load_config(repo_root)
    except ConfigLoadError:
        loaded = None
    output_format = format.strip().lower()
    export_formats: tuple[str, ...] | None = None
    if output_format != "text":
        try:
            export_formats = normalize_release_asset_formats((output_format,))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--format") from exc

    snapshot = build_release_asset_snapshot(
        loaded=loaded,
        repo_root=repo_root,
        target_version=version,
        target_tag=tag,
        build=build,
        smoke_install=smoke_install,
    )
    if export_formats is None:
        typer.echo(render_release_asset_text(snapshot), nl=False)
        if snapshot["summary"]["status"] == "issues":
            raise typer.Exit(code=1)
        return

    output_path = _resolve_operator_report_output(
        repo_root=repo_root,
        loaded=loaded,
        output=output,
        default_name="release-assets",
    )
    result = build_release_asset_exports(
        snapshot=snapshot,
        output_path=output_path,
        formats=export_formats,
    )
    _print_operator_report_exports("Release assets", result.output_paths)
    typer.echo(f"- asset_summary: {result.asset_summary_path}")
    typer.echo(
        "Release assets summary: "
        f"status={result.snapshot['summary']['status']} "
        f"target={result.snapshot['target']['tag']} "
        f"artifacts={result.snapshot['summary']['artifact_count']} "
        f"smoke_install={result.snapshot['smoke_install']['status']}"
    )
    if result.snapshot["summary"]["status"] == "issues":
        raise typer.Exit(code=1)


@app.command("version")
def version_command() -> None:
    typer.echo(__version__)


def _resolve_upgrade_inputs(
    repo_root: Path,
    preset: str | None,
    tracker_kind: str | None,
    tracker_repo: str | None,
    tracker_path: str | None,
    fixture_issues: str | None,
) -> tuple[str, str, str, str | None, str | None]:
    try:
        loaded = load_config(repo_root)
    except ConfigLoadError as exc:
        typer.echo(
            "Upgrade requires an existing RepoAgents installation. Run `repoagents init` first.",
            err=True,
        )
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    detected_preset = detect_scaffold_preset(repo_root)
    preset_name = preset or detected_preset
    if not preset_name:
        typer.echo(
            "Could not detect the installed preset. Pass `--preset` explicitly when using `repoagents init --upgrade`.",
            err=True,
        )
        raise typer.Exit(code=1)
    if preset_name not in PRESETS:
        typer.echo(
            f"Unknown preset '{preset_name}'. Available presets: {', '.join(sorted(PRESETS))}",
            err=True,
        )
        raise typer.Exit(code=2)
    return (
        preset_name,
        _normalize_tracker_kind(tracker_kind or loaded.data.tracker.kind.value),
        tracker_repo or loaded.data.tracker.repo or f"local/{repo_root.name}",
        tracker_path or loaded.data.tracker.path,
        fixture_issues or loaded.data.tracker.fixtures_path,
    )


def _should_prompt_for_init(
    interactive: bool | None,
    preset: str | None,
    tracker_kind: str | None,
    tracker_repo: str | None,
    tracker_path: str | None,
    fixture_issues: str | None,
) -> bool:
    if interactive is not None:
        return interactive
    return all(value is None for value in (preset, tracker_kind, tracker_repo, tracker_path, fixture_issues))


def _prompt_init_inputs(
    repo_root: Path,
    preset: str | None,
    tracker_kind: str | None,
    tracker_repo: str | None,
    tracker_path: str | None,
    fixture_issues: str | None,
) -> tuple[str, str, str, str | None, str | None]:
    preset_name = _prompt_choice(
        "Preset",
        current=preset,
        default="python-library",
        options=_preset_choice_options(),
    )
    resolved_tracker_kind = _prompt_choice(
        "Tracker kind",
        current=tracker_kind,
        default="github",
        options=[
            ChoiceOption("github", "github", "Use a GitHub issue tracker."),
            ChoiceOption("local_file", "local_file", "Use a local JSON issue inbox."),
            ChoiceOption("local_markdown", "local_markdown", "Use a local Markdown issue directory."),
        ],
    )
    if resolved_tracker_kind == "github":
        default_tracker_repo = tracker_repo or _default_github_tracker_repo(repo_root)
        target_repo = typer.prompt(
            "Tracker repo",
            default=default_tracker_repo,
        ).strip()
        if not _looks_like_github_repo_slug(target_repo):
            typer.echo("Tracker repo must look like owner/name.", err=True)
            raise typer.Exit(code=2)
        target_repo = _ensure_interactive_github_tracker_repo(target_repo)
        resolved_tracker_path = tracker_path
    else:
        target_repo = tracker_repo or f"local/{repo_root.name}"
        resolved_tracker_path = typer.prompt(
            "Tracker path",
            default=tracker_path or ("issues" if resolved_tracker_kind == "local_markdown" else "issues.json"),
        ).strip()
    fixture_path = fixture_issues if resolved_tracker_kind == "github" else None
    if resolved_tracker_kind == "github" and fixture_path is None:
        use_fixture = typer.confirm(
            "Use local fixture issues file?",
            default=(repo_root / "issues.json").exists(),
        )
        if use_fixture:
            fixture_path = typer.prompt("Fixture issues path", default="issues.json").strip()
    return (
        preset_name,
        resolved_tracker_kind,
        target_repo,
        resolved_tracker_path,
        fixture_path,
    )


def _prompt_choice(
    label: str,
    *,
    current: str | None,
    default: str,
    options: list[ChoiceOption],
) -> str:
    allowed = [option.value for option in options]
    resolved_default = current if current in allowed else default
    if _supports_arrow_choice_prompt():
        return _prompt_choice_with_arrows(
            label,
            current=current,
            default=resolved_default,
            options=options,
        )
    chosen = typer.prompt(
        f"{label} [{'/'.join(allowed)}]",
        default=resolved_default,
    ).strip()
    normalized = chosen.strip()
    if normalized not in allowed:
        typer.echo(
            f"Invalid {label.lower()} '{normalized}'. Expected one of: {', '.join(allowed)}.",
            err=True,
        )
        raise typer.Exit(code=2)
    return normalized


def _preset_choice_options() -> list[ChoiceOption]:
    options = [ChoiceOption("none", "No preset", PRESETS["none"].description)]
    for preset_name in INIT_PRESET_ORDER:
        if preset_name == "none":
            continue
        preset = PRESETS[preset_name]
        options.append(ChoiceOption(preset_name, preset_name, preset.description))
    return options


def _default_github_tracker_repo(repo_root: Path) -> str:
    origin_repo = _read_origin_repo_slug(repo_root)
    if origin_repo:
        return origin_repo
    gh_login = _read_gh_login()
    if gh_login:
        return f"{gh_login}/{repo_root.name}"
    return f"local/{repo_root.name}"


def _read_origin_repo_slug(repo_root: Path) -> str | None:
    if not is_git_repository(repo_root):
        return None
    try:
        remote_url = run_git(["remote", "get-url", "origin"], repo_root)
    except GitCommandError:
        return None
    return extract_git_remote_repo_slug(remote_url)


def _read_gh_login() -> str | None:
    if shutil.which("gh") is None:
        return None
    auth = subprocess.run(
        ["gh", "auth", "status", "--hostname", "github.com"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if auth.returncode != 0:
        return None
    completed = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        return None
    login = completed.stdout.strip()
    return login or None


def _looks_like_github_repo_slug(value: str) -> bool:
    parts = [part.strip() for part in value.split("/")]
    return len(parts) == 2 and all(parts)


def _ensure_interactive_github_tracker_repo(tracker_repo: str) -> str:
    probe = _probe_github_tracker_repo(tracker_repo)
    if probe.status == "exists":
        return tracker_repo
    if probe.status != "missing":
        if probe.message:
            typer.echo(f"Skipping tracker repo verification for {tracker_repo}: {probe.message}")
        return tracker_repo

    typer.echo(f"GitHub tracker repo `{tracker_repo}` was not found.")
    create_repo = typer.confirm("Create it now with gh?", default=True)
    if not create_repo:
        return tracker_repo

    visibility = _prompt_choice(
        "GitHub repo visibility",
        current=None,
        default="private",
        options=[
            ChoiceOption("private", "private", "Only invited collaborators can access it."),
            ChoiceOption("public", "public", "Anyone can view the tracker repo."),
        ],
    )
    _create_github_tracker_repo(tracker_repo, visibility)
    typer.echo(f"Created GitHub tracker repo `{tracker_repo}` ({visibility}).")
    return tracker_repo


def _probe_github_tracker_repo(tracker_repo: str) -> GitHubRepoProbe:
    gh_path = shutil.which("gh")
    if gh_path is None:
        return GitHubRepoProbe("unknown", "gh is not installed")

    auth = subprocess.run(
        ["gh", "auth", "status", "--hostname", "github.com"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if auth.returncode != 0:
        return GitHubRepoProbe("unknown", "gh is installed but not authenticated")

    completed = subprocess.run(
        ["gh", "repo", "view", tracker_repo, "--json", "nameWithOwner"],
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )
    if completed.returncode == 0:
        return GitHubRepoProbe("exists")

    output = "\n".join(part.strip() for part in (completed.stderr, completed.stdout) if part.strip())
    lowered = output.lower()
    if any(
        marker in lowered
        for marker in (
            "not found",
            "could not resolve to a repository",
            "could not resolve repository",
            "repository not found",
        )
    ):
        return GitHubRepoProbe("missing")
    return GitHubRepoProbe("unknown", output or "gh repo view failed")


def _create_github_tracker_repo(tracker_repo: str, visibility: str) -> None:
    completed = subprocess.run(
        ["gh", "repo", "create", tracker_repo, f"--{visibility}"],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode == 0:
        return
    output = "\n".join(part.strip() for part in (completed.stderr, completed.stdout) if part.strip())
    typer.echo(
        f"Failed to create GitHub tracker repo `{tracker_repo}`: {output or 'unknown gh error'}",
        err=True,
    )
    raise typer.Exit(code=2)


def _supports_arrow_choice_prompt() -> bool:
    term = os.environ.get("TERM", "").strip().lower()
    return sys.stdin.isatty() and sys.stdout.isatty() and term not in {"", "dumb"}


def _prompt_choice_with_arrows(
    label: str,
    *,
    current: str | None,
    default: str,
    options: list[ChoiceOption],
) -> str:
    selected_index = _resolve_choice_index(options, current=current, default=default)
    rendered_lines = 0
    cursor_hidden = False
    try:
        click.echo("\x1b[?25l", nl=False)
        cursor_hidden = True
        while True:
            rendered_lines = _render_arrow_choice_prompt(label, options, selected_index, rendered_lines)
            key = _read_choice_key()
            if key == "up":
                selected_index = (selected_index - 1) % len(options)
                continue
            if key == "down":
                selected_index = (selected_index + 1) % len(options)
                continue
            if key == "enter":
                click.echo()
                return options[selected_index].value
            if key == "interrupt":
                raise click.Abort()
    finally:
        if cursor_hidden:
            click.echo("\x1b[?25h", nl=False)


def _resolve_choice_index(options: list[ChoiceOption], *, current: str | None, default: str) -> int:
    allowed = [option.value for option in options]
    selected_value = current if current in allowed else default
    for index, option in enumerate(options):
        if option.value == selected_value:
            return index
    return 0


def _render_arrow_choice_prompt(
    label: str,
    options: list[ChoiceOption],
    selected_index: int,
    rendered_lines: int,
) -> int:
    if rendered_lines:
        click.echo(f"\x1b[{rendered_lines}F", nl=False)
    prompt_lines = [f"{label} (use arrow keys and Enter)"]
    for index, option in enumerate(options):
        is_selected = index == selected_index
        marker = click.style(">", fg="blue") if is_selected else " "
        display_label = option.label if option.label == option.value else f"{option.label} [{option.value}]"
        label_text = click.style(display_label, fg="blue") if is_selected else display_label
        line = f"{marker} {label_text}"
        if option.detail:
            line = f"{line} {click.style(option.detail, fg='bright_black')}"
        prompt_lines.append(line)
    for line in prompt_lines:
        click.echo(f"\x1b[2K{line}")
    return len(prompt_lines)


def _read_choice_key() -> str:
    char = click.getchar()
    if any(marker in char for marker in ("\r", "\n")):
        return "enter"
    if "\x03" in char:
        return "interrupt"
    if char in {"k", "K"}:
        return "up"
    if char in {"j", "J"}:
        return "down"
    if char in {"\x1b[A", "\x1bOA"}:
        return "up"
    if char in {"\x1b[B", "\x1bOB"}:
        return "down"
    if char == "\x1b":
        next_char = click.getchar()
        if next_char in {"[A", "OA"}:
            return "up"
        if next_char in {"[B", "OB"}:
            return "down"
        if next_char == "[":
            direction = click.getchar()
            if direction == "A":
                return "up"
            if direction == "B":
                return "down"
        return "other"
    return "other"

def _normalize_tracker_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"github", "local_file", "local_markdown"}:
        typer.echo(
            f"Invalid tracker kind '{value}'. Expected one of: github, local_file, local_markdown.",
            err=True,
        )
        raise typer.Exit(code=2)
    return normalized

def _doctor_requires_codex_command(loaded: LoadedConfig | None) -> bool:
    del loaded
    return True


def _collect_clean_actions(
    loaded: LoadedConfig,
    records: list[RunRecord],
    issue_filter: int | None = None,
    *,
    include_sync_applied: bool = False,
    sync_keep_groups_per_issue: int = 20,
) -> list[CleanAction]:
    actions: list[CleanAction] = []
    seen_paths: set[str] = set()
    tracked_runs = {(record.issue_id, record.run_id) for record in records}

    for record in records:
        if record.status in {RunLifecycle.IN_PROGRESS, RunLifecycle.RETRY_PENDING}:
            continue
        if record.workspace_path:
            workspace_path = Path(record.workspace_path)
            if workspace_path.exists():
                _append_clean_action(
                    actions,
                    seen_paths,
                    CleanAction(
                        kind="workspace",
                        path=workspace_path,
                        issue_id=record.issue_id,
                        run_id=record.run_id,
                        state_updated=True,
                    ),
                )
        artifact_path = loaded.artifacts_dir / f"issue-{record.issue_id}" / record.run_id
        if artifact_path.exists():
            _append_clean_action(
                actions,
                seen_paths,
                CleanAction(
                    kind="artifacts",
                    path=artifact_path,
                    issue_id=record.issue_id,
                    run_id=record.run_id,
                    state_updated=True,
                ),
            )

    for root, kind in (
        (loaded.workspace_root, "workspace-orphan"),
        (loaded.artifacts_dir, "artifacts-orphan"),
    ):
        if not root.exists():
            continue
        for issue_root in sorted(root.glob("issue-*")):
            if not issue_root.is_dir():
                continue
            issue_id = _parse_issue_root_id(issue_root.name)
            if issue_id is None:
                continue
            if issue_filter is not None and issue_id != issue_filter:
                continue
            for run_root in sorted(issue_root.iterdir()):
                if not run_root.is_dir():
                    continue
                if (issue_id, run_root.name) in tracked_runs:
                    continue
                target = run_root / "repo" if kind == "workspace-orphan" and (run_root / "repo").exists() else run_root
                _append_clean_action(
                    actions,
                    seen_paths,
                    CleanAction(kind=kind, path=target, issue_id=issue_id, run_id=run_root.name),
                )
    if include_sync_applied:
        _collect_sync_applied_clean_actions(
            loaded,
            actions,
            seen_paths,
            issue_filter=issue_filter,
            keep_groups_per_issue=sync_keep_groups_per_issue,
        )
    return actions


def _append_clean_action(
    actions: list[CleanAction],
    seen_paths: set[str],
    action: CleanAction,
) -> None:
    key = str(action.path.resolve())
    if key in seen_paths:
        return
    seen_paths.add(key)
    actions.append(action)


def _resolve_sync_applied_manifest_archive_path(
    loaded: LoadedConfig,
    entry: dict[str, Any],
) -> Path | None:
    archived_relative_path = entry.get("archived_relative_path")
    if isinstance(archived_relative_path, str) and archived_relative_path:
        return (loaded.sync_applied_dir / archived_relative_path).resolve()
    archived_path = entry.get("archived_path")
    if isinstance(archived_path, str) and archived_path:
        return Path(archived_path).resolve()
    return None


def _sync_manifest_group_key(entry: dict[str, Any], *, index: int) -> str:
    handoff = entry.get("handoff")
    if isinstance(handoff, dict):
        group_key = handoff.get("group_key")
        if isinstance(group_key, str) and group_key:
            return group_key
    for key in ("entry_key", "source_relative_path", "archived_relative_path"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return f"entry-{index}"


def _sync_manifest_sort_key(entry: dict[str, Any], *, index: int) -> tuple[str, int]:
    for key in ("applied_at", "staged_at"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return (value, index)
    return ("", index)


def _select_sync_manifest_group_keys(
    entries: list[dict[str, Any]],
    keep_groups_per_issue: int,
) -> set[str]:
    groups: dict[str, tuple[str, int]] = {}
    for index, entry in enumerate(entries):
        group_key = _sync_manifest_group_key(entry, index=index)
        sort_key = _sync_manifest_sort_key(entry, index=index)
        existing = groups.get(group_key)
        if existing is None or sort_key > existing:
            groups[group_key] = sort_key
    ordered = sorted(groups.items(), key=lambda item: item[1], reverse=True)
    return {group_key for group_key, _sort_key in ordered[:keep_groups_per_issue]}


def _count_sync_manifest_groups(entries: list[dict[str, Any]]) -> int:
    return len({_sync_manifest_group_key(entry, index=index) for index, entry in enumerate(entries)})


def _parse_issue_root_id(name: str) -> int | None:
    if not name.startswith("issue-"):
        return None
    suffix = name.removeprefix("issue-")
    return int(suffix) if suffix.isdigit() else None


def _execute_clean_actions(
    loaded: LoadedConfig,
    actions: list[CleanAction],
    store: RunStateStore,
) -> None:
    updated_issue_ids: set[int] = set()
    for action in actions:
        if action.kind.startswith("workspace"):
            _cleanup_workspace_path(loaded, action.path)
        elif action.kind.startswith("artifacts"):
            shutil.rmtree(action.path)
            _prune_empty_parent_dirs(action.path.parent, loaded.artifacts_dir)
        elif action.kind == "sync-applied-archive":
            if action.path.exists():
                action.path.unlink()
            _prune_empty_parent_dirs(action.path.parent, loaded.sync_applied_dir)
        elif action.kind == "sync-applied-issue-root":
            if action.path.exists():
                shutil.rmtree(action.path)
            _prune_empty_parent_dirs(action.path.parent, loaded.sync_applied_dir)
        elif action.kind == "sync-applied-manifest":
            replacement_payload = action.replacement_payload
            if not isinstance(replacement_payload, list):
                replacement_payload = []
            write_json_file(action.path, replacement_payload)
        if action.state_updated and action.issue_id is not None:
            record = store.get(action.issue_id)
            if record is None:
                continue
            if action.kind == "workspace":
                record.workspace_path = None
            elif action.kind == "artifacts":
                record.role_artifacts = {}
            updated_issue_ids.add(action.issue_id)
    for issue_id in sorted(updated_issue_ids):
        record = store.get(issue_id)
        if record is not None:
            store.upsert(record)


def _sync_applied_issue_exists(loaded: LoadedConfig, issue_id: int) -> bool:
    return any(loaded.sync_applied_dir.glob(f"*/issue-{issue_id}"))


def _collect_sync_applied_clean_actions(
    loaded: LoadedConfig,
    actions: list[CleanAction],
    seen_paths: set[str],
    *,
    issue_filter: int | None,
    keep_groups_per_issue: int,
) -> None:
    if not loaded.sync_applied_dir.exists():
        return

    for tracker_root in sorted(loaded.sync_applied_dir.iterdir()):
        if not tracker_root.is_dir():
            continue
        for issue_root in sorted(tracker_root.glob("issue-*")):
            if not issue_root.is_dir():
                continue
            issue_id = _parse_issue_root_id(issue_root.name)
            if issue_filter is not None and issue_id != issue_filter:
                continue
            _collect_sync_applied_issue_actions(
                loaded,
                issue_root=issue_root,
                issue_id=issue_id,
                keep_groups_per_issue=keep_groups_per_issue,
                actions=actions,
                seen_paths=seen_paths,
            )


def _collect_sync_applied_issue_actions(
    loaded: LoadedConfig,
    *,
    issue_root: Path,
    issue_id: int | None,
    keep_groups_per_issue: int,
    actions: list[CleanAction],
    seen_paths: set[str],
) -> None:
    manifest_path = issue_root / "manifest.json"
    existing_files = sorted(
        path for path in issue_root.iterdir() if path.is_file() and path.name != "manifest.json"
    )
    if not manifest_path.exists():
        if not existing_files and not any(issue_root.iterdir()):
            _append_clean_action(
                actions,
                seen_paths,
                CleanAction(
                    kind="sync-applied-issue-root",
                    path=issue_root,
                    issue_id=issue_id,
                    detail="empty issue archive directory",
                ),
            )
        return

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(payload, list):
        return

    valid_entries: list[dict[str, Any]] = []
    invalid_count = 0
    dangling_count = 0
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            invalid_count += 1
            continue
        archived_path = _resolve_sync_applied_manifest_archive_path(loaded, entry)
        if archived_path is None or not archived_path.exists():
            dangling_count += 1
            continue
        valid_entries.append(entry)

    keep_group_keys = _select_sync_manifest_group_keys(valid_entries, keep_groups_per_issue)
    kept_entries = [
        entry
        for index, entry in enumerate(valid_entries)
        if _sync_manifest_group_key(entry, index=index) in keep_group_keys
    ]
    trimmed_entries = len(valid_entries) - len(kept_entries)
    kept_paths = {
        archived_path.resolve()
        for entry in kept_entries
        if (archived_path := _resolve_sync_applied_manifest_archive_path(loaded, entry)) is not None
    }
    removable_files: dict[str, Path] = {}
    for file_path in existing_files:
        resolved_path = file_path.resolve()
        if resolved_path not in kept_paths:
            removable_files[str(resolved_path)] = file_path

    if not kept_entries and not kept_paths and manifest_path.exists():
        _append_clean_action(
            actions,
            seen_paths,
            CleanAction(
                kind="sync-applied-issue-root",
                path=issue_root,
                issue_id=issue_id,
                detail=(
                    f"remove applied sync archive directory "
                    f"(dangling_entries={dangling_count}, trimmed_entries={trimmed_entries}, orphans={len(removable_files)})"
                ),
            ),
        )
        return

    manifest_changed = invalid_count > 0 or dangling_count > 0 or trimmed_entries > 0
    if manifest_changed:
        _append_clean_action(
            actions,
            seen_paths,
            CleanAction(
                kind="sync-applied-manifest",
                path=manifest_path,
                issue_id=issue_id,
                replacement_payload=kept_entries,
                detail=(
                    f"keep_groups={len(keep_group_keys)}/{_count_sync_manifest_groups(valid_entries)} "
                    f"trimmed_entries={trimmed_entries} dangling_entries={dangling_count} invalid_entries={invalid_count}"
                ),
            ),
        )

    for file_path in sorted(removable_files.values()):
        _append_clean_action(
            actions,
            seen_paths,
            CleanAction(
                kind="sync-applied-archive",
                path=file_path,
                issue_id=issue_id,
                detail="unreferenced applied sync artifact",
            ),
        )


def _cleanup_workspace_path(loaded: LoadedConfig, workspace_path: Path) -> None:
    copy_manager = CopyWorkspaceManager(loaded.repo_root, loaded.workspace_root)
    worktree_manager = WorktreeWorkspaceManager(loaded.repo_root, loaded.workspace_root)
    if workspace_path.name == "repo":
        try:
            if (workspace_path / ".git").exists():
                asyncio.run(worktree_manager.cleanup_workspace(workspace_path))
                return
            asyncio.run(copy_manager.cleanup_workspace(workspace_path))
            return
        except Exception:  # noqa: BLE001
            fallback_root = workspace_path.parent if workspace_path.parent.exists() else workspace_path
            shutil.rmtree(fallback_root)
            _prune_empty_parent_dirs(fallback_root.parent, loaded.workspace_root)
        return
    shutil.rmtree(workspace_path)
    _prune_empty_parent_dirs(workspace_path.parent, loaded.workspace_root)


def _prune_empty_parent_dirs(path: Path, stop_root: Path) -> None:
    current = path
    resolved_stop = stop_root.resolve()
    while current.exists() and current.resolve() != resolved_stop:
        if any(current.iterdir()):
            break
        current.rmdir()
        current = current.parent


def _load_or_exit() -> LoadedConfig:
    try:
        return load_config(resolve_repo_root(Path.cwd()))
    except ConfigLoadError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def _run_version(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        return f"(version probe failed: {exc})"
    return completed.stdout or completed.stderr or "(no version output)"


def _indent_block(text: str, prefix: str = "  ") -> str:
    return "\n".join(f"{prefix}{line}" for line in text.splitlines())


def _print_tracker_status(loaded: LoadedConfig) -> None:
    tracker = loaded.data.tracker
    if tracker.kind.value == "github":
        typer.echo(
            f"Tracker: kind={tracker.kind} repo={tracker.repo} mode={tracker.mode} poll={tracker.poll_interval_seconds}s"
        )
        if tracker.mode == "fixture":
            fixture_path = loaded.resolve(tracker.fixtures_path or "")
            typer.echo(f"Fixture issues: {'OK' if fixture_path.exists() else 'MISSING'} ({fixture_path})")
        else:
            token_present = bool(os.getenv(tracker.token_env))
            typer.echo(
                "GitHub auth: "
                + (
                    f"{tracker.token_env} available for REST API access"
                    if token_present
                    else f"set {tracker.token_env} for live REST API access"
                )
            )
        return

    tracker_path = loaded.resolve(tracker.path or "issues.json")
    typer.echo(
        f"Tracker: kind={tracker.kind} path={tracker_path} poll={tracker.poll_interval_seconds}s"
    )
    tracker_label = "Local tracker directory" if tracker.kind.value == "local_markdown" else "Local tracker file"
    typer.echo(f"{tracker_label}: {'OK' if tracker_path.exists() else 'MISSING'} ({tracker_path})")


def _print_required_files(loaded: LoadedConfig) -> None:
    required = _required_managed_files(loaded)
    missing = [path for path in required if not path.exists()]
    if missing:
        typer.echo("Managed files: MISSING")
        for path in missing:
            typer.echo(f"- {path}")
    else:
        typer.echo("Managed files: OK")


def _print_workspace_status(loaded: LoadedConfig, working_tree: WorkingTreeStatus) -> None:
    strategy = loaded.data.workspace.strategy
    dirty_policy = loaded.data.workspace.dirty_policy.value
    typer.echo(f"Workspace: strategy={strategy} root={loaded.workspace_root}")
    if strategy == "worktree":
        typer.echo(
            "Workspace git support: "
            + (
                "OK"
                if working_tree.is_git_repo
                else "MISSING (repository is not a git work tree)"
            )
        )
    if not working_tree.is_git_repo:
        typer.echo(f"Working tree: NOT_APPLICABLE policy={dirty_policy}")
        _print_logging_status(loaded)
        return
    if not working_tree.dirty_entries:
        typer.echo(f"Working tree: CLEAN policy={dirty_policy}")
        _print_logging_status(loaded)
        return
    typer.echo(
        f"Working tree: DIRTY policy={dirty_policy} changes={_summarize_dirty_entries(working_tree.dirty_entries)}"
    )
    _print_logging_status(loaded)


def _print_logging_status(loaded: LoadedConfig) -> None:
    typer.echo(
        "Logging: "
        f"json={loaded.data.logging.json_logs} "
        f"file_enabled={loaded.data.logging.file_enabled} "
        f"dir={loaded.logs_dir}"
    )


def _resolve_operator_report_output(
    *,
    repo_root: Path,
    loaded: LoadedConfig | None,
    output: Path | None,
    default_name: str,
) -> Path:
    if output is not None:
        if loaded is not None:
            return loaded.resolve(output)
        if output.is_absolute():
            return output
        return (repo_root / output).resolve()
    if loaded is not None:
        return loaded.reports_dir / f"{default_name}.json"
    return (repo_root / ".ai-repoagents" / "reports" / f"{default_name}.json").resolve()


def _print_operator_report_exports(label: str, output_paths: dict[str, Path]) -> None:
    typer.echo(f"{label} exports:")
    for export_format, path in output_paths.items():
        typer.echo(f"- {export_format}: {path}")


def _serialize_diagnostic_check(check: DiagnosticCheck) -> dict[str, object]:
    return {
        "name": check.name,
        "status": check.status,
        "message": check.message,
        "hint": check.hint,
        "detail_lines": list(check.detail_lines),
    }


def _collect_tracker_snapshot(loaded: LoadedConfig) -> dict[str, object]:
    tracker = loaded.data.tracker
    snapshot: dict[str, object] = {
        "kind": tracker.kind.value,
        "mode": tracker.mode.value,
        "repo": tracker.repo,
        "path": str(loaded.resolve(tracker.path or "issues.json")),
        "poll_interval_seconds": tracker.poll_interval_seconds,
    }
    if tracker.kind.value == "github":
        snapshot["api_url"] = tracker.api_url
        snapshot["token_env"] = tracker.token_env
        snapshot["fixtures_path"] = tracker.fixtures_path
        return snapshot

    tracker_path = loaded.resolve(tracker.path or "issues.json")
    expected_kind = "directory" if tracker.kind.value == "local_markdown" else "file"
    if not tracker_path.exists():
        snapshot["path_status"] = "missing"
    elif expected_kind == "directory" and not tracker_path.is_dir():
        snapshot["path_status"] = "wrong_type"
    elif expected_kind == "file" and tracker_path.is_dir():
        snapshot["path_status"] = "wrong_type"
    else:
        snapshot["path_status"] = "ok"
    return snapshot


def _collect_workspace_snapshot(
    loaded: LoadedConfig,
    working_tree: WorkingTreeStatus,
) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "strategy": loaded.data.workspace.strategy,
        "root": str(loaded.workspace_root),
        "dirty_policy": loaded.data.workspace.dirty_policy.value,
        "is_git_repo": working_tree.is_git_repo,
        "dirty_entries": list(working_tree.dirty_entries),
    }
    if loaded.data.workspace.strategy == "worktree":
        snapshot["git_support_status"] = "ok" if working_tree.is_git_repo else "missing"
    if not working_tree.is_git_repo:
        snapshot["working_tree_status"] = "not_applicable"
    elif not working_tree.dirty_entries:
        snapshot["working_tree_status"] = "clean"
    else:
        snapshot["working_tree_status"] = "dirty"
        snapshot["dirty_summary"] = _summarize_dirty_entries(working_tree.dirty_entries)
    return snapshot


def _collect_logging_snapshot(loaded: LoadedConfig) -> dict[str, object]:
    return {
        "json_logs": loaded.data.logging.json_logs,
        "file_enabled": loaded.data.logging.file_enabled,
        "directory": str(loaded.logs_dir),
        "level": loaded.data.logging.level,
    }


def _required_managed_files(loaded: LoadedConfig) -> list[Path]:
    return [
        loaded.ai_root / "repoagents.yaml",
        loaded.ai_root / "roles" / "triage.md",
        loaded.ai_root / "roles" / "planner.md",
        loaded.ai_root / "roles" / "engineer.md",
        loaded.ai_root / "roles" / "qa.md",
        loaded.ai_root / "roles" / "reviewer.md",
        loaded.ai_root / "prompts" / "triage.txt.j2",
        loaded.ai_root / "prompts" / "planner.txt.j2",
        loaded.ai_root / "prompts" / "engineer.txt.j2",
        loaded.ai_root / "prompts" / "qa.txt.j2",
        loaded.ai_root / "prompts" / "reviewer.txt.j2",
        loaded.ai_root / "policies" / "merge-policy.md",
        loaded.ai_root / "policies" / "scope-policy.md",
        loaded.state_dir / "runs.json",
        loaded.repo_root / "AGENTS.md",
        loaded.repo_root / "WORKFLOW.md",
        loaded.repo_root / ".github" / "workflows" / "repoagents-check.yml",
    ]


def _collect_managed_files_snapshot(loaded: LoadedConfig) -> dict[str, object]:
    required = _required_managed_files(loaded)
    missing = [str(path) for path in required if not path.exists()]
    return {
        "status": "ok" if not missing else "missing",
        "required_count": len(required),
        "missing_count": len(missing),
        "missing": missing,
    }


def _build_doctor_snapshot(
    *,
    repo_root: Path,
    loaded: LoadedConfig | None,
    config_error: str | None,
    codex_command: str,
    command_path: str | None,
    codex_version: str | None,
    codex_required: bool,
    diagnostic_checks: list[DiagnosticCheck],
    working_tree: WorkingTreeStatus | None,
    exit_code: int,
) -> dict[str, object]:
    diagnostic_counts = Counter(check.status for check in diagnostic_checks)
    if exit_code != 0:
        overall_status = "issues"
    elif diagnostic_counts.get("WARN", 0):
        overall_status = "attention"
    else:
        overall_status = "clean"

    snapshot: dict[str, object] = {
        "meta": {
            "kind": "doctor",
            "rendered_at": utc_now().isoformat(),
            "repo_root": str(repo_root),
        },
        "summary": {
            "overall_status": overall_status,
            "exit_code": exit_code,
            "diagnostic_count": len(diagnostic_checks),
            "diagnostic_status_counts": dict(sorted(diagnostic_counts.items())),
        },
        "config": {
            "status": "ok" if loaded is not None else "error",
            "path": str(loaded.config_path if loaded is not None else (repo_root / ".ai-repoagents" / "repoagents.yaml")),
            "error": config_error,
        },
        "codex": {
            "command": codex_command,
            "status": "ok" if command_path else ("skipped" if not codex_required else "missing"),
            "required": codex_required,
            "path": command_path,
            "version": codex_version,
        },
        "diagnostics": [_serialize_diagnostic_check(check) for check in diagnostic_checks],
    }
    if loaded is not None:
        snapshot["tracker"] = _collect_tracker_snapshot(loaded)
        if working_tree is not None:
            snapshot["workspace"] = _collect_workspace_snapshot(loaded, working_tree)
        snapshot["logging"] = _collect_logging_snapshot(loaded)
        snapshot["managed_files"] = _collect_managed_files_snapshot(loaded)
    return snapshot


def _build_status_snapshot(
    *,
    loaded: LoadedConfig,
    all_records: list[RunRecord],
    selected_records: list[RunRecord],
    issue_filter: int | None,
    report_health_snapshot: dict[str, object],
    ops_snapshot: dict[str, object],
    policy_alignment: ReportPolicyExportAlignment,
    policy_health: ReportPolicyHealth,
) -> dict[str, object]:
    selected_counts = Counter(record.status.value for record in selected_records)
    all_counts = Counter(record.status.value for record in all_records)
    detail_lines = _build_related_report_details_lines(
        title="related report details:",
        mismatch_warnings=(),
        policy_drift_warnings=tuple(
            _format_report_policy_mismatch(mismatch) for mismatch in policy_alignment.mismatches
        ),
        remediation=_report_policy_drift_guidance_detail(),
        show_mismatches=False,
        show_remediation=True,
        prefix="  ",
    )
    return {
        "meta": {
            "kind": "status",
            "rendered_at": utc_now().isoformat(),
            "repo_root": str(loaded.repo_root),
            "config_path": str(loaded.config_path),
            "state_path": str(loaded.state_dir / "runs.json"),
            "issue_filter": issue_filter,
        },
        "summary": {
            "total_runs": len(all_records),
            "selected_runs": len(selected_records),
            "all_by_status": dict(sorted(all_counts.items())),
            "selected_by_status": dict(sorted(selected_counts.items())),
        },
        "report_health": {
            **report_health_snapshot,
            "policy_alignment": {
                "status": "mismatch" if policy_alignment.mismatches else (
                    "match" if policy_alignment.comparable_reports else "not_applicable"
                ),
                "current_summary": policy_alignment.current_summary,
                "comparable_reports": policy_alignment.comparable_reports,
                "mismatch_count": len(policy_alignment.mismatches),
                "mismatches": [
                    {
                        "file_name": mismatch.file_name,
                        "embedded_summary": mismatch.embedded_summary,
                        "current_summary": mismatch.current_summary,
                    }
                    for mismatch in policy_alignment.mismatches
                ],
                "detail_lines": list(detail_lines),
            },
            "policy_health": {
                "severity": policy_health.severity,
                "status": policy_health.status,
                "message": policy_health.message,
                "hint": policy_health.hint,
            },
        },
        "ops_snapshots": ops_snapshot,
        "runs": [record.model_dump(mode="json") for record in selected_records],
    }


def _build_ops_snapshot_cleanup_components(
    *,
    loaded: LoadedConfig,
    bundle_root: Path,
    records: list[RunRecord],
    issue_filter: int | None,
    include_cleanup_preview: bool,
    include_cleanup_result: bool,
    cleanup_sync_applied: bool,
    cleanup_keep_groups: int | None,
) -> dict[str, dict[str, object]]:
    components: dict[str, dict[str, object]] = {}

    if include_cleanup_preview:
        resolved_keep_groups = cleanup_keep_groups or loaded.data.cleanup.sync_applied_keep_groups_per_issue
        actions = _collect_clean_actions(
            loaded,
            records,
            issue_filter=issue_filter,
            include_sync_applied=cleanup_sync_applied,
            sync_keep_groups_per_issue=resolved_keep_groups,
        )
        preview_result = build_cleanup_report(
            loaded,
            actions=actions,
            dry_run=True,
            include_sync_applied=cleanup_sync_applied,
            issue_id=issue_filter,
            sync_keep_groups_per_issue=resolved_keep_groups if cleanup_sync_applied else None,
            output_path=bundle_root / "cleanup-preview.json",
            formats=("json", "markdown"),
        )
        components["cleanup_preview"] = {
            "status": "attention" if preview_result.action_count else "clean",
            "label": "Cleanup preview",
            "reason": "generated cleanup preview in ops snapshot bundle",
            "output_paths": preview_result.output_paths,
            "mode": preview_result.mode,
            "action_count": preview_result.action_count,
            "related_sync_audit_reports": preview_result.related_sync_audit_reports,
            "sync_audit_policy_drifts": preview_result.sync_audit_policy_drifts,
            "link_to_sync_audit": True,
        }

    if include_cleanup_result:
        source_json = loaded.reports_dir / "cleanup-result.json"
        source_markdown = loaded.reports_dir / "cleanup-result.md"
        if source_json.exists():
            copied_paths: dict[str, Path] = {}
            target_json = bundle_root / "cleanup-result.json"
            write_text_file(target_json, source_json.read_text(encoding="utf-8"))
            copied_paths["json"] = target_json
            if source_markdown.exists():
                target_markdown = bundle_root / "cleanup-result.md"
                write_text_file(target_markdown, source_markdown.read_text(encoding="utf-8"))
                copied_paths["markdown"] = target_markdown
            snapshot = _load_report_json_payload(source_json)
            summary = snapshot.get("summary")
            if not isinstance(summary, dict):
                summary = {}
            overall_status = summary.get("overall_status")
            action_count = summary.get("action_count", 0)
            related_sync_audit_reports = summary.get("related_sync_audit_reports", 0)
            sync_audit_policy_drifts = summary.get("sync_audit_policy_drifts", 0)
            status = "clean" if overall_status in {"clean", "cleaned", "ok"} else "attention"
            components["cleanup_result"] = {
                "status": status,
                "label": "Cleanup result",
                "reason": "copied existing cleanup result into ops snapshot bundle",
                "output_paths": copied_paths,
                "mode": "applied",
                "action_count": action_count,
                "related_sync_audit_reports": related_sync_audit_reports,
                "sync_audit_policy_drifts": sync_audit_policy_drifts,
                "link_to_sync_audit": True,
            }
        else:
            components["cleanup_result"] = {
                "status": "missing",
                "label": "Cleanup result",
                "reason": "requested cleanup result inclusion but no cleanup-result.json exists under .ai-repoagents/reports",
                "output_paths": {},
                "link_to_sync_audit": False,
            }

    return components


def _build_ops_snapshot_sync_components(
    *,
    loaded: LoadedConfig,
    bundle_root: Path,
    issue_filter: int | None,
    tracker_filter: str | None,
    include_sync_check: bool,
    include_sync_repair_preview: bool,
) -> dict[str, dict[str, object]]:
    components: dict[str, dict[str, object]] = {}

    if include_sync_check:
        check_result = build_sync_check_report(
            loaded,
            output_path=bundle_root / "sync-check.json",
            formats=("json", "markdown"),
            issue_id=issue_filter,
            tracker=tracker_filter,
        )
        components["sync_check"] = {
            "status": check_result.overall_status,
            "label": "Sync check",
            "reason": "generated sync check report in ops snapshot bundle",
            "output_paths": check_result.output_paths,
            "report_count": check_result.total_reports,
            "issues_with_findings": check_result.issues_with_findings,
            "total_findings": check_result.total_findings,
            "link_targets": ("sync_audit",),
        }

    if include_sync_repair_preview:
        repair_result = build_sync_repair_report(
            loaded,
            dry_run=True,
            output_path=bundle_root / "sync-repair-preview.json",
            formats=("json", "markdown"),
            issue_id=issue_filter,
            tracker=tracker_filter,
        )
        components["sync_repair_preview"] = {
            "status": repair_result.overall_status,
            "label": "Sync repair preview",
            "reason": "generated sync repair preview in ops snapshot bundle",
            "output_paths": repair_result.output_paths,
            "mode": "preview",
            "report_count": repair_result.total_reports,
            "changed_reports": repair_result.changed_reports,
            "findings_before": repair_result.findings_before,
            "findings_after": repair_result.findings_after,
            "dropped_entries": repair_result.dropped_entries,
            "adopted_archives": repair_result.adopted_archives,
            "normalized_entries": repair_result.normalized_entries,
            "link_targets": ("sync_audit", "sync_check"),
        }

    return components


def _build_ops_snapshot_sync_health_artifacts(
    *,
    loaded: LoadedConfig,
    bundle_root: Path,
    records: list[RunRecord],
    issue_filter: int | None,
    tracker_filter: str | None,
    sync_limit: int,
    cleanup_sync_applied: bool,
    cleanup_keep_groups: int | None,
) -> tuple[SyncHealthBuildResult, dict[str, Path], dict[str, object]]:
    resolved_keep_groups = cleanup_keep_groups or loaded.data.cleanup.sync_applied_keep_groups_per_issue
    cleanup_actions = _collect_clean_actions(
        loaded,
        records,
        issue_filter=issue_filter,
        include_sync_applied=cleanup_sync_applied,
        sync_keep_groups_per_issue=resolved_keep_groups,
    )
    bundle_result = build_sync_health_report(
        loaded,
        cleanup_actions=cleanup_actions,
        issue_id=issue_filter,
        tracker=tracker_filter,
        limit=sync_limit,
        cleanup_include_sync_applied=cleanup_sync_applied,
        cleanup_keep_groups_per_issue=resolved_keep_groups if cleanup_sync_applied else None,
        output_path=bundle_root / "sync-health.json",
        formats=("json", "markdown"),
    )
    root_paths = {
        "json": loaded.reports_dir / "sync-health.json",
        "markdown": loaded.reports_dir / "sync-health.md",
    }
    write_text_file(root_paths["json"], bundle_result.output_paths["json"].read_text(encoding="utf-8"))
    write_text_file(
        root_paths["markdown"],
        bundle_result.output_paths["markdown"].read_text(encoding="utf-8"),
    )
    summary = bundle_result.snapshot.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    component = {
        "status": bundle_result.overall_status,
        "label": "Sync health",
        "reason": "generated sync health report in ops snapshot bundle",
        "output_paths": bundle_result.output_paths,
        "pending_artifacts": bundle_result.pending_artifacts,
        "integrity_issue_count": bundle_result.integrity_issue_count,
        "repair_changed_reports": bundle_result.repair_changed_reports,
        "repair_findings_after": bundle_result.repair_findings_after,
        "cleanup_action_count": bundle_result.cleanup_action_count,
        "cleanup_sync_applied_action_count": summary.get("cleanup_sync_applied_action_count", 0),
        "prunable_groups": summary.get("prunable_groups", 0),
        "repair_needed_issues": summary.get("repair_needed_issues", 0),
        "related_cleanup_reports": bundle_result.related_cleanup_reports,
        "related_sync_audit_reports": bundle_result.related_sync_audit_reports,
        "related_report_mismatches": summary.get("related_report_mismatches", 0),
        "related_report_policy_drifts": summary.get("related_report_policy_drifts", 0),
        "next_action_count": len(bundle_result.next_actions),
        "link_targets": ("sync_audit", "cleanup_preview", "cleanup_result"),
    }
    return bundle_result, root_paths, component


def _build_ops_snapshot_github_smoke_artifacts(
    *,
    loaded: LoadedConfig,
    bundle_root: Path,
    issue_filter: int | None,
    issue_limit: int,
) -> tuple[GitHubSmokeBuildResult, GitHubSmokeBuildResult, dict[str, object]] | None:
    if loaded.data.tracker.kind.value != "github" or loaded.data.tracker.mode.value != "rest":
        return None

    tracker = build_tracker(loaded, dry_run=False)
    try:
        snapshot = asyncio.run(
            build_github_smoke_snapshot(
                loaded=loaded,
                tracker=tracker,
                issue_id=issue_filter,
                issue_limit=max(1, issue_limit),
            )
        )
    finally:
        asyncio.run(tracker.aclose())

    bundle_result = build_github_smoke_exports(
        snapshot=snapshot,
        output_path=bundle_root / "github-smoke.json",
        formats=("json", "markdown"),
    )
    root_result = build_github_smoke_exports(
        snapshot=snapshot,
        output_path=loaded.reports_dir / "github-smoke.json",
        formats=("json", "markdown"),
    )
    summary = snapshot.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    repo_access = snapshot.get("repo_access")
    if not isinstance(repo_access, dict):
        repo_access = {}
    branch_policy = snapshot.get("branch_policy")
    if not isinstance(branch_policy, dict):
        branch_policy = {}
    publish = snapshot.get("publish")
    if not isinstance(publish, dict):
        publish = {}
    component = {
        "status": summary.get("status", "attention"),
        "label": "GitHub smoke",
        "reason": "generated GitHub smoke report in ops snapshot bundle",
        "output_paths": bundle_result.output_paths,
        "open_issue_count": summary.get("open_issue_count", 0),
        "sampled_issue_id": summary.get("sampled_issue_id"),
        "repo_access_status": repo_access.get("status", "unknown"),
        "default_branch": repo_access.get("default_branch"),
        "branch_policy_status": branch_policy.get("status", "unknown"),
        "publish_status": publish.get("status", "unknown"),
        "link_targets": ("ops_brief", "ops_status"),
    }
    return bundle_result, root_result, component


def _build_ops_snapshot_ops_brief_artifacts(
    *,
    loaded: LoadedConfig,
    bundle_root: Path,
    issue_filter: int | None,
    tracker_filter: str | None,
    doctor_snapshot: dict[str, Any],
    status_snapshot: dict[str, Any],
    dashboard_snapshot: dict[str, Any],
    sync_audit_snapshot: dict[str, Any],
    sync_health_snapshot: dict[str, Any],
    github_smoke_snapshot: dict[str, Any] | None = None,
) -> tuple[OpsBriefBuildResult, OpsBriefBuildResult, dict[str, object]]:
    snapshot = build_ops_brief_snapshot(
        repo_root=loaded.repo_root,
        config_path=loaded.config_path,
        issue_filter=issue_filter,
        tracker_filter=tracker_filter,
        doctor_snapshot=doctor_snapshot,
        status_snapshot=status_snapshot,
        dashboard_snapshot=dashboard_snapshot,
        sync_audit_snapshot=sync_audit_snapshot,
        sync_health_snapshot=sync_health_snapshot,
        github_smoke_snapshot=github_smoke_snapshot,
    )
    bundle_result = build_ops_brief_exports(
        snapshot=snapshot,
        output_path=bundle_root / "ops-brief.json",
        formats=("json", "markdown"),
    )
    root_result = build_ops_brief_exports(
        snapshot=snapshot,
        output_path=loaded.reports_dir / "ops-brief.json",
        formats=("json", "markdown"),
    )
    component = {
        "status": bundle_result.severity,
        "label": "Ops brief",
        "reason": "generated operator-facing handoff brief in ops snapshot bundle",
        "output_paths": bundle_result.output_paths,
        "headline": bundle_result.headline,
        "top_finding_count": bundle_result.top_finding_count,
        "next_action_count": bundle_result.next_action_count,
        "top_findings": bundle_result.snapshot.get("top_findings", []),
        "next_actions": bundle_result.snapshot.get("next_actions", []),
        "github_smoke_status": (
            bundle_result.snapshot.get("summary", {}).get("github_smoke_status", "not_applicable")
            if isinstance(bundle_result.snapshot.get("summary"), dict)
            else "not_applicable"
        ),
        "link_targets": ("status", "sync_audit", "sync_health", "ops_status", "github_smoke"),
    }
    return bundle_result, root_result, component


def _build_ops_snapshot_ops_status_artifacts(
    *,
    loaded: LoadedConfig,
    bundle_root: Path,
    snapshot: dict[str, Any],
) -> tuple[OpsStatusBuildResult, OpsStatusBuildResult, dict[str, object]]:
    bundle_result = build_ops_status_exports(
        snapshot=snapshot,
        output_path=bundle_root / "ops-status.json",
        formats=("json", "markdown"),
    )
    root_result = build_ops_status_exports(
        snapshot=snapshot,
        output_path=loaded.reports_dir / "ops-status.json",
        formats=("json", "markdown"),
    )

    summary = snapshot.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    related_reports = snapshot.get("related_reports")
    if not isinstance(related_reports, dict):
        related_reports = {}
    raw_related_entries = related_reports.get("entries")
    related_entries = raw_related_entries if isinstance(raw_related_entries, list) else []
    report_key_to_component = {
        "ops-brief": "ops_brief",
        "github-smoke": "github_smoke",
        "sync-audit": "sync_audit",
        "sync-health": "sync_health",
        "cleanup-preview": "cleanup_preview",
        "cleanup-result": "cleanup_result",
    }
    link_targets: list[str] = []
    for entry in related_entries:
        if not isinstance(entry, dict):
            continue
        report_key = entry.get("key")
        if not isinstance(report_key, str):
            continue
        component_key = report_key_to_component.get(report_key)
        if component_key is not None and component_key not in link_targets:
            link_targets.append(component_key)

    component = {
        "status": summary.get("status", "attention"),
        "label": "Ops status",
        "reason": "generated ops status report in ops snapshot bundle",
        "output_paths": bundle_result.output_paths,
        "index_status": summary.get("index_status", "unknown"),
        "latest_bundle_status": summary.get("latest_bundle_status", "unknown"),
        "history_entry_count": summary.get("history_entry_count", 0),
        "history_limit": summary.get("history_limit", 0),
        "archive_entry_count": summary.get("archive_entry_count", 0),
        "related_report_count": summary.get("related_report_count", 0),
        "link_targets": tuple(link_targets),
    }
    return bundle_result, root_result, component


def _load_report_json_payload(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _collect_doctor_checks(loaded: LoadedConfig) -> list[DiagnosticCheck]:
    policy_alignment = _collect_report_policy_export_alignment(loaded)
    checks: list[DiagnosticCheck]
    if loaded.data.tracker.kind.value == "github":
        auth_snapshot = collect_github_auth_snapshot(loaded)
        origin_snapshot = collect_github_origin_snapshot(loaded)
        repo_access_snapshot, branch_policy_snapshot = asyncio.run(
            collect_github_live_repo_snapshots(loaded)
        )
        checks = [
            _probe_github_auth(loaded, auth_snapshot=auth_snapshot),
            _probe_github_network(loaded),
            _probe_github_repo_access(
                loaded,
                auth_snapshot=auth_snapshot,
                snapshot=repo_access_snapshot,
            ),
            _probe_github_branch_policy(
                loaded,
                snapshot=branch_policy_snapshot,
            ),
            _probe_github_publish_readiness(
                loaded,
                auth_snapshot=auth_snapshot,
                origin_snapshot=origin_snapshot,
                repo_access_snapshot=repo_access_snapshot,
                branch_policy_snapshot=branch_policy_snapshot,
            ),
        ]
    else:
        checks = [
            _probe_local_tracker(loaded),
        ]
    checks.extend(
        [
            _probe_report_freshness_policy(loaded),
            _probe_report_policy_export_alignment(loaded, policy_alignment=policy_alignment),
            _probe_report_policy_health(loaded, policy_alignment=policy_alignment),
            _probe_write_permissions(loaded),
            _probe_template_drift(loaded),
        ]
    )
    return checks


def _print_diagnostic_check(check: DiagnosticCheck) -> None:
    typer.echo(f"{check.name}: {check.status} ({check.message})")
    if check.hint:
        typer.echo(f"  hint: {check.hint}")
    for line in check.detail_lines:
        typer.echo(line)


def _probe_github_auth(
    loaded: LoadedConfig,
    *,
    auth_snapshot: dict[str, Any] | None = None,
) -> DiagnosticCheck:
    snapshot = auth_snapshot or collect_github_auth_snapshot(loaded)
    status = str(snapshot.get("status") or "warn").upper()
    normalized_status = {
        "OK": "OK",
        "WARN": "WARN",
        "NOT_APPLICABLE": "NOT_APPLICABLE",
    }.get(status, "WARN")
    return DiagnosticCheck(
        name="GitHub auth",
        status=normalized_status,
        message=str(snapshot.get("message") or "unknown GitHub auth state"),
        hint=snapshot.get("hint") if isinstance(snapshot.get("hint"), str) else None,
    )


def _probe_github_network(loaded: LoadedConfig) -> DiagnosticCheck:
    if loaded.data.tracker.mode.value == "fixture":
        return DiagnosticCheck(
            name="GitHub network",
            status="NOT_APPLICABLE",
            message="fixture tracker mode does not contact the GitHub API",
        )
    if loaded.data.tracker.smoke_fixture_path:
        return DiagnosticCheck(
            name="GitHub network",
            status="NOT_APPLICABLE",
            message="configured GitHub smoke fixture bypasses live GitHub network probes",
        )
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv(loaded.data.tracker.token_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{loaded.data.tracker.api_url.rstrip('/')}/rate_limit"
    try:
        response = httpx.get(
            url,
            headers=headers,
            timeout=5.0,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return DiagnosticCheck(
            name="GitHub network",
            status="WARN",
            message=f"could not reach {url}: {exc}",
            hint="Check network connectivity, proxy settings, or tracker.api_url.",
        )
    return DiagnosticCheck(
        name="GitHub network",
        status="OK",
        message=f"{url} reachable (status {response.status_code})",
    )


def _probe_github_repo_access(
    loaded: LoadedConfig,
    *,
    auth_snapshot: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> DiagnosticCheck:
    if snapshot is not None:
        status = str(snapshot.get("status") or "warn")
        normalized_status = {
            "ok": "OK",
            "warn": "WARN",
            "issues": "ERROR",
            "not_applicable": "NOT_APPLICABLE",
        }.get(status, "WARN")
        hint: str | None = None
        if normalized_status == "ERROR":
            auth = auth_snapshot or collect_github_auth_snapshot(loaded)
            token_env = loaded.data.tracker.token_env
            hint = (
                f"Set {token_env} for private repos or verify tracker.repo is readable."
                if not auth.get("token_present")
                else "Verify tracker.repo and token permissions."
            )
        return DiagnosticCheck(
            name="GitHub repo access",
            status=normalized_status,
            message=str(snapshot.get("message") or "unknown GitHub repo access state"),
            hint=hint,
        )

    if loaded.data.tracker.mode.value == "fixture":
        return DiagnosticCheck(
            name="GitHub repo access",
            status="NOT_APPLICABLE",
            message="fixture tracker mode does not probe live repo metadata",
        )
    headers = {"Accept": "application/vnd.github+json"}
    token_env = loaded.data.tracker.token_env
    token = os.getenv(token_env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{loaded.data.tracker.api_url.rstrip('/')}/repos/{loaded.data.tracker.repo}"
    try:
        response = httpx.get(
            url,
            headers=headers,
            timeout=5.0,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return DiagnosticCheck(
            name="GitHub repo access",
            status="WARN",
            message=f"could not reach {url}: {exc}",
            hint="Check network connectivity, tracker.repo, or tracker.api_url.",
        )
    if response.status_code >= 400:
        auth = auth_snapshot or collect_github_auth_snapshot(loaded)
        hint = (
            f"Set {token_env} for private repos or verify tracker.repo is readable."
            if not auth.get("token_present")
            else "Verify tracker.repo and token permissions."
        )
        return DiagnosticCheck(
            name="GitHub repo access",
            status="ERROR",
            message=f"{url} returned status {response.status_code}",
            hint=hint,
        )
    payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    default_branch = payload.get("default_branch") if isinstance(payload, dict) else None
    visibility = "private" if isinstance(payload, dict) and payload.get("private") else "public"
    details = f"default_branch={default_branch}" if default_branch else "default_branch=unknown"
    return DiagnosticCheck(
        name="GitHub repo access",
        status="OK",
        message=f"{loaded.data.tracker.repo} reachable ({visibility}; {details})",
    )


def _probe_github_branch_policy(
    loaded: LoadedConfig,
    *,
    snapshot: dict[str, Any] | None = None,
) -> DiagnosticCheck:
    branch_policy = snapshot
    if branch_policy is None:
        _, branch_policy = asyncio.run(collect_github_live_repo_snapshots(loaded))
    status = str(branch_policy.get("status") or "warn")
    normalized_status = {
        "ok": "OK",
        "warn": "WARN",
        "issues": "ERROR",
        "not_applicable": "NOT_APPLICABLE",
    }.get(status, "WARN")
    warnings = branch_policy.get("warnings")
    notes = branch_policy.get("notes")
    detail_lines: tuple[str, ...] = ()
    if isinstance(warnings, tuple) and warnings:
        detail_lines = tuple(
            [f"  - {warning}" for warning in warnings if isinstance(warning, str)]
        )
    if isinstance(notes, tuple) and notes:
        detail_lines = detail_lines + tuple(
            f"  note: {note}" for note in notes if isinstance(note, str)
        )
    return DiagnosticCheck(
        name="GitHub branch policy",
        status=normalized_status,
        message=str(branch_policy.get("message") or "unknown default-branch policy"),
        hint=branch_policy.get("hint") if isinstance(branch_policy.get("hint"), str) else None,
        detail_lines=detail_lines,
    )


def _probe_github_publish_readiness(
    loaded: LoadedConfig,
    *,
    auth_snapshot: dict[str, Any] | None = None,
    origin_snapshot: dict[str, Any] | None = None,
    repo_access_snapshot: dict[str, Any] | None = None,
    branch_policy_snapshot: dict[str, Any] | None = None,
) -> DiagnosticCheck:
    snapshot = collect_github_publish_readiness(
        loaded,
        auth_snapshot=auth_snapshot,
        origin_snapshot=origin_snapshot,
        repo_access_snapshot=repo_access_snapshot,
        branch_policy_snapshot=branch_policy_snapshot,
    )
    status = str(snapshot.get("status") or "warn")
    normalized_status = {
        "ok": "OK",
        "warn": "WARN",
        "not_applicable": "NOT_APPLICABLE",
    }.get(status, "WARN")
    warnings = snapshot.get("warnings")
    detail_lines = ()
    if isinstance(warnings, tuple) and warnings:
        detail_lines = tuple(f"  - {warning}" for warning in warnings if isinstance(warning, str))
    return DiagnosticCheck(
        name="GitHub publish readiness",
        status=normalized_status,
        message=str(snapshot.get("message") or "unknown live publish readiness"),
        hint=snapshot.get("hint") if isinstance(snapshot.get("hint"), str) else None,
        detail_lines=detail_lines,
    )


def _probe_report_freshness_policy(loaded: LoadedConfig) -> DiagnosticCheck:
    summary = _format_report_freshness_policy_summary(loaded)
    if _is_default_report_freshness_policy(loaded):
        return DiagnosticCheck(
            name="Report freshness policy",
            status="OK",
            message=f"default thresholds ({summary})",
        )
    warning = _report_freshness_policy_warning(loaded)
    if warning is not None:
        message, hint = warning
        return DiagnosticCheck(
            name="Report freshness policy",
            status="WARN",
            message=message,
            hint=hint,
        )
    return DiagnosticCheck(
        name="Report freshness policy",
        status="OK",
        message=f"custom thresholds ({summary})",
    )


def _probe_report_policy_export_alignment(
    loaded: LoadedConfig,
    *,
    policy_alignment: ReportPolicyExportAlignment | None = None,
) -> DiagnosticCheck:
    alignment = policy_alignment or _collect_report_policy_export_alignment(loaded)
    if alignment.comparable_reports == 0:
        return DiagnosticCheck(
            name="Report policy export alignment",
            status="NOT_APPLICABLE",
            message="no raw report exports with embedded policy metadata found",
        )
    if alignment.mismatches:
        return DiagnosticCheck(
            name="Report policy export alignment",
            status="WARN",
            message=(
                f"{len(alignment.mismatches)} raw report exports use a different embedded policy"
            ),
            detail_lines=_build_related_report_details_lines(
                title="related report details:",
                mismatch_warnings=(),
                policy_drift_warnings=tuple(
                    _format_report_policy_mismatch(item) for item in alignment.mismatches
                ),
                remediation=_report_policy_drift_guidance_detail(),
                show_mismatches=False,
                show_remediation=True,
                prefix="  ",
            ),
        )
    return DiagnosticCheck(
        name="Report policy export alignment",
        status="OK",
        message=(
            f"{alignment.comparable_reports} raw report exports match current thresholds "
            f"({alignment.current_summary})"
        ),
    )


def _probe_report_policy_health(
    loaded: LoadedConfig,
    *,
    policy_alignment: ReportPolicyExportAlignment | None = None,
) -> DiagnosticCheck:
    health = _collect_report_policy_health(
        loaded,
        policy_alignment=policy_alignment,
    )
    return DiagnosticCheck(
        name="Report policy health",
        status=health.status,
        message=health.message,
        hint=health.hint,
    )


def _probe_local_tracker(loaded: LoadedConfig) -> DiagnosticCheck:
    tracker_path = loaded.resolve(loaded.data.tracker.path or "issues.json")
    tracker_kind = loaded.data.tracker.kind.value
    if tracker_kind == "local_markdown":
        if not tracker_path.exists():
            return DiagnosticCheck(
                name="Local tracker directory",
                status="ERROR",
                message=f"{tracker_path} does not exist",
                hint="Create the Markdown issue directory or update tracker.path.",
            )
        if not tracker_path.is_dir():
            return DiagnosticCheck(
                name="Local tracker directory",
                status="ERROR",
                message=f"{tracker_path} is not a directory",
                hint="Point tracker.path at a directory containing Markdown issue files.",
            )
        markdown_count = len(list(tracker_path.glob("*.md")))
        return DiagnosticCheck(
            name="Local tracker directory",
            status="OK",
            message=f"{tracker_path} is readable with {markdown_count} markdown issue file(s)",
        )
    if not tracker_path.exists():
        return DiagnosticCheck(
            name="Local tracker file",
            status="ERROR",
            message=f"{tracker_path} does not exist",
            hint="Create the issue file or update tracker.path.",
        )
    return DiagnosticCheck(
        name="Local tracker file",
        status="OK",
        message=f"{tracker_path} is readable",
    )


def _probe_write_permissions(loaded: LoadedConfig) -> DiagnosticCheck:
    targets = {
        "workspace": loaded.workspace_root,
        "artifacts": loaded.artifacts_dir,
        "state": loaded.state_dir,
    }
    if loaded.data.logging.file_enabled:
        targets["logs"] = loaded.logs_dir
    failures: list[str] = []
    for label, path in targets.items():
        try:
            ensure_dir(path)
            probe_path = path / ".repoagents-write-check"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{label}={path} ({exc})")
    if failures:
        return DiagnosticCheck(
            name="Write permissions",
            status="ERROR",
            message="one or more RepoAgents directories are not writable",
            hint="; ".join(failures),
        )
    return DiagnosticCheck(
        name="Write permissions",
        status="OK",
        message="workspace, artifacts, and state directories are writable",
    )


def _probe_template_drift(loaded: LoadedConfig) -> DiagnosticCheck:
    preset_name = detect_scaffold_preset(loaded.repo_root)
    if not preset_name:
        return DiagnosticCheck(
            name="Template drift",
            status="WARN",
            message="could not determine the installed preset",
            hint="Run `repoagents init --upgrade` to inspect managed scaffold drift, or pass `--preset` explicitly.",
        )

    expected_files = render_managed_file_map(
        preset_name=preset_name,
        tracker_repo=loaded.data.tracker.repo or f"local/{loaded.repo_root.name}",
        fixture_issues=loaded.data.tracker.fixtures_path,
        tracker_kind=loaded.data.tracker.kind.value,
        tracker_path=loaded.data.tracker.path,
    )
    drifted: list[str] = []
    ignored = {Path(".ai-repoagents/repoagents.yaml")}
    for rel_path, expected_body in expected_files.items():
        if rel_path in ignored:
            continue
        path = loaded.repo_root / rel_path
        if not path.exists():
            continue
        if path.read_text(encoding="utf-8") != expected_body:
            drifted.append(str(rel_path))

    agents_path = loaded.repo_root / "AGENTS.md"
    if agents_path.exists():
        actual_block = extract_managed_block(agents_path.read_text(encoding="utf-8"))
        expected_block = render_agents_block(
            preset_name=preset_name,
            tracker_repo=loaded.data.tracker.repo or f"local/{loaded.repo_root.name}",
            fixture_issues=loaded.data.tracker.fixtures_path,
            tracker_kind=loaded.data.tracker.kind.value,
            tracker_path=loaded.data.tracker.path,
        ).strip()
        if actual_block != expected_block:
            drifted.append("AGENTS.md#managed-block")

    if drifted:
        return DiagnosticCheck(
            name="Template drift",
            status="WARN",
            message=f"{len(drifted)} managed files differ from the packaged scaffold",
            hint="Review local changes or run `repoagents init --upgrade` to inspect drift. "
            + "Use `repoagents init --upgrade --force` to refresh managed files. "
            + ", ".join(drifted[:5]),
        )
    return DiagnosticCheck(
        name="Template drift",
        status="OK",
        message="managed scaffold files match the packaged templates",
    )


def _get_working_tree_status(loaded: LoadedConfig) -> WorkingTreeStatus:
    is_repo = is_git_repository(loaded.repo_root)
    dirty_entries = list_dirty_working_tree_entries(loaded.repo_root) if is_repo else []
    return WorkingTreeStatus(is_git_repo=is_repo, dirty_entries=dirty_entries)


def _workspace_doctor_has_error(loaded: LoadedConfig, working_tree: WorkingTreeStatus) -> bool:
    if loaded.data.workspace.strategy == "worktree" and not working_tree.is_git_repo:
        return True
    return (
        loaded.data.workspace.dirty_policy.value == "block"
        and bool(working_tree.dirty_entries)
    )


def _enforce_workspace_run_policy(loaded: LoadedConfig) -> None:
    working_tree = _get_working_tree_status(loaded)
    if loaded.data.workspace.strategy == "worktree" and not working_tree.is_git_repo:
        typer.echo(
            "Workspace policy blocked run: workspace.strategy=worktree requires the target repository to be a git work tree.",
            err=True,
        )
        raise typer.Exit(code=1)
    if not working_tree.is_git_repo or not working_tree.dirty_entries:
        return

    dirty_policy = loaded.data.workspace.dirty_policy.value
    summary = _summarize_dirty_entries(working_tree.dirty_entries)
    if dirty_policy == "block":
        typer.echo(
            f"Workspace policy blocked run: dirty working tree detected ({summary}).",
            err=True,
        )
        raise typer.Exit(code=1)
    if dirty_policy == "warn":
        typer.echo(
            f"Workspace policy warning: dirty working tree detected ({summary}). Continuing because workspace.dirty_policy=warn.",
            err=True,
        )


def _summarize_dirty_entries(entries: list[str], limit: int = 5) -> str:
    preview = ", ".join(entries[:limit])
    if len(entries) > limit:
        preview = f"{preview}, ... (+{len(entries) - limit} more)"
    return preview


def _print_run_record(record: RunRecord) -> None:
    typer.echo(
        f"- issue={record.issue_id} run_id={record.run_id} status={record.status} "
        f"attempts={record.attempts} backend={record.backend_mode} "
        f"updated_at={record.updated_at.isoformat()} current_role={record.current_role or '-'}"
    )
    if record.next_retry_at:
        typer.echo(f"  next_retry_at: {record.next_retry_at.isoformat()}")
    if record.workspace_path:
        typer.echo(f"  workspace: {record.workspace_path}")
    if record.summary:
        typer.echo(f"  summary: {record.summary}")
    if record.last_error:
        typer.echo(f"  last_error: {record.last_error}")
    if record.external_actions:
        typer.echo("  external_actions:")
        for action in record.external_actions:
            typer.echo(
                f"    - {action.action}: executed={action.executed} reason={action.reason}"
            )


def _print_status_report_health(
    snapshot: dict[str, object],
    *,
    policy_alignment: ReportPolicyExportAlignment | None = None,
    policy_health: ReportPolicyHealth | None = None,
    ops_snapshot: dict[str, object] | None = None,
) -> None:
    hero = snapshot.get("hero")
    policy = snapshot.get("policy")
    reports = snapshot.get("reports")
    if not isinstance(hero, dict) or not isinstance(reports, dict):
        return
    typer.echo(
        "Report health: "
        f"severity={hero.get('severity', 'unknown')} "
        f"title={hero.get('title', 'n/a')} "
        f"reports={reports.get('total', 0)}"
    )
    if isinstance(policy, dict):
        typer.echo(f"  policy: {policy.get('summary', 'n/a')}")
    if policy_health is not None:
        typer.echo(f"  policy_health: {policy_health.severity} | {policy_health.message}")
    if policy_alignment is not None and policy_alignment.mismatches:
        typer.echo(
            "  policy_warning: "
            f"{len(policy_alignment.mismatches)} raw report exports use a different embedded policy"
        )
        for line in _build_related_report_details_lines(
            title="related report details:",
            mismatch_warnings=(),
            policy_drift_warnings=tuple(
                _format_report_policy_mismatch(mismatch) for mismatch in policy_alignment.mismatches
            ),
            remediation=_report_policy_drift_guidance_detail(),
            show_mismatches=False,
            show_remediation=True,
            prefix="  ",
        ):
            typer.echo(line)
    typer.echo(
        "  overall: "
        f"{reports.get('freshness_severity', 'unknown')} | "
        f"{_format_status_report_freshness(reports.get('freshness'))} | "
        f"{reports.get('freshness_severity_reason', 'n/a')}"
    )
    if int(reports.get("cleanup_total", 0) or 0) > 0:
        typer.echo(
            "  cleanup: "
            f"{reports.get('cleanup_freshness_severity', 'unknown')} | "
            f"{_format_status_report_freshness(reports.get('cleanup_freshness'))} | "
            f"{reports.get('cleanup_freshness_severity_reason', 'n/a')}"
        )
    if isinstance(ops_snapshot, dict):
        typer.echo(
            "Ops snapshots: "
            f"status={ops_snapshot.get('status', 'missing')} "
            f"entries={ops_snapshot.get('history_entry_count', 0)}/"
            f"{ops_snapshot.get('history_limit', 0)} "
            f"archives={ops_snapshot.get('archive_entry_count', 0)} "
            f"dropped={ops_snapshot.get('dropped_entry_count', 0)}"
        )
        latest = ops_snapshot.get("latest")
        if isinstance(latest, dict) and latest:
            typer.echo(
                "  latest: "
                f"{latest.get('entry_id', 'n/a')} | "
                f"{latest.get('overall_status', 'unknown')} | "
                f"age={latest.get('age_human', 'n/a')}"
            )
            typer.echo(
                f"  bundle: {latest.get('bundle_dir', 'n/a')}"
            )
            if latest.get("archive_path"):
                typer.echo(f"  archive: {latest['archive_path']}")


def _format_status_report_freshness(value: object) -> str:
    if not isinstance(value, dict):
        return "none"
    fresh = int(value.get("fresh", 0) or 0)
    aging = int(value.get("aging", 0) or 0)
    stale = int(value.get("stale", 0) or 0)
    future = int(value.get("future", 0) or 0)
    unknown = int(value.get("unknown", 0) or 0)
    total = fresh + aging + stale + future + unknown
    if total == 0:
        return "none"
    parts = [
        f"fresh {fresh}",
        f"aging {aging}",
        f"stale {stale}",
    ]
    if future:
        parts.append(f"future {future}")
    if unknown:
        parts.append(f"unknown {unknown}")
    return " · ".join(parts) + f" / {total} total"


def _is_default_report_freshness_policy(loaded: LoadedConfig) -> bool:
    policy = loaded.data.dashboard.report_freshness_policy
    return (
        policy.unknown_issues_threshold,
        policy.stale_issues_threshold,
        policy.future_attention_threshold,
        policy.aging_attention_threshold,
    ) == (1, 1, 1, 1)


def _report_freshness_policy_warning(loaded: LoadedConfig) -> tuple[str, str] | None:
    policy = loaded.data.dashboard.report_freshness_policy
    summary = _format_report_freshness_policy_summary(loaded)
    if policy.unknown_issues_threshold > 5 or policy.stale_issues_threshold > 5:
        return (
            f"issue escalation is heavily relaxed ({summary})",
            "Dashboard report health may stay below `issues` until several stale or "
            "unknown reports accumulate.",
        )
    if policy.future_attention_threshold > 10 or policy.aging_attention_threshold > 10:
        return (
            f"attention escalation is heavily relaxed ({summary})",
            "Aging or future-dated reports may stay quiet longer than operators expect. "
            "Consider lower dashboard.report_freshness_policy thresholds.",
        )
    return None


def _collect_report_policy_health(
    loaded: LoadedConfig,
    *,
    policy_alignment: ReportPolicyExportAlignment | None = None,
) -> ReportPolicyHealth:
    alignment = policy_alignment or _collect_report_policy_export_alignment(loaded)
    summary = _format_report_freshness_policy_summary(loaded)
    warning = _report_freshness_policy_warning(loaded)
    message_parts: list[str] = []
    hint_parts: list[str] = []

    if warning is not None:
        warning_message, warning_hint = warning
        message_parts.append(warning_message)
        hint_parts.append(warning_hint)
    else:
        message_parts.append(f"thresholds {summary}")

    mismatch_count = len(alignment.mismatches)
    if mismatch_count:
        export_label = "export uses" if mismatch_count == 1 else "exports use"
        message_parts.append(
            f"{mismatch_count} raw report {export_label} a different embedded policy"
        )
        return ReportPolicyHealth(
            severity="attention",
            status="WARN",
            message="; ".join(message_parts),
            hint="; ".join(hint_parts) if hint_parts else None,
        )

    if warning is not None:
        return ReportPolicyHealth(
            severity="attention",
            status="WARN",
            message="; ".join(message_parts),
            hint="; ".join(hint_parts) if hint_parts else None,
        )

    if alignment.comparable_reports > 0:
        message_parts.append(
            f"{alignment.comparable_reports} raw report exports match current policy"
        )
    return ReportPolicyHealth(
        severity="clean",
        status="OK",
        message="; ".join(message_parts),
        hint=None,
    )


def _collect_report_policy_export_alignment(loaded: LoadedConfig) -> ReportPolicyExportAlignment:
    current_summary = _format_report_freshness_policy_summary(loaded)
    comparable_reports = 0
    mismatches: list[ReportPolicyMismatch] = []
    for file_name in RAW_POLICY_REPORT_EXPORTS:
        embedded_summary = _load_report_policy_summary(loaded.reports_dir / file_name)
        if embedded_summary is None:
            continue
        comparable_reports += 1
        if embedded_summary != current_summary:
            mismatches.append(
                ReportPolicyMismatch(
                    file_name=file_name,
                    embedded_summary=embedded_summary,
                    current_summary=current_summary,
                )
            )
    return ReportPolicyExportAlignment(
        current_summary=current_summary,
        comparable_reports=comparable_reports,
        mismatches=tuple(mismatches),
    )


def _load_report_policy_summary(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    policy = payload.get("policy")
    if not isinstance(policy, dict):
        return None
    summary = policy.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return None


def _format_report_policy_mismatch(mismatch: ReportPolicyMismatch) -> str:
    return (
        f"{mismatch.file_name} embedded={mismatch.embedded_summary} "
        f"current={mismatch.current_summary}"
    )


def _report_policy_drift_guidance_detail() -> str:
    return build_report_policy_drift_guidance()["detail"]


def _format_report_freshness_policy_summary(loaded: LoadedConfig) -> str:
    policy = loaded.data.dashboard.report_freshness_policy
    return (
        f"unknown>={policy.unknown_issues_threshold} "
        f"stale>={policy.stale_issues_threshold} "
        f"future>={policy.future_attention_threshold} "
        f"aging>={policy.aging_attention_threshold}"
    )


def _print_dry_run_preview(preview: DryRunPreview) -> None:
    typer.echo(f"Issue #{preview.issue_id}: {preview.title}")
    typer.echo(f"  selected: {preview.selected}")
    typer.echo(f"  backend: {preview.backend_mode}")
    typer.echo(f"  roles: {', '.join(preview.roles_to_invoke)}")
    typer.echo(f"  likely_files: {', '.join(preview.likely_files) if preview.likely_files else 'none'}")
    typer.echo(f"  policy: {preview.policy_summary}")
    typer.echo(f"  blocked_side_effects: {'; '.join(preview.blocked_side_effects)}")
    typer.echo(f"  summary: {preview.summary}")
    typer.echo("  comment_preview:")
    typer.echo(_indent_block(preview.comment_preview, prefix="    "))
    typer.echo(f"  pr_title_preview: {preview.pr_title_preview}")
    typer.echo("  pr_body_preview:")
    typer.echo(_indent_block(preview.pr_body_preview, prefix="    "))
    typer.echo("")


def _print_cleanup_report_build_result(report_result: CleanupReportBuildResult) -> None:
    typer.echo("Cleanup report exports:")
    for export_format, path in report_result.output_paths.items():
        typer.echo(f"- {export_format}: {path}")
    typer.echo(
        f"Cleanup report summary: mode={report_result.mode} actions={report_result.action_count}"
    )
    if report_result.related_sync_audit_reports:
        typer.echo(f"Related sync audit reports: {report_result.related_sync_audit_reports}")
    if report_result.sync_audit_issue_filter_mismatches:
        typer.echo(
            "Sync audit issue filter mismatches: "
            f"{report_result.sync_audit_issue_filter_mismatches}"
        )
    if report_result.sync_audit_policy_drifts:
        typer.echo(f"Sync audit policy drifts: {report_result.sync_audit_policy_drifts}")


def _print_cleanup_report_build_result_with_options(
    report_result: CleanupReportBuildResult,
    *,
    show_remediation: bool,
    show_mismatches: bool,
) -> None:
    _print_cleanup_report_build_result(report_result)
    _print_related_report_details_block(
        title="Related sync audit details:",
        mismatch_warnings=report_result.sync_audit_mismatch_warnings,
        policy_drift_warnings=report_result.sync_audit_policy_drift_warnings,
        remediation=report_result.policy_drift_guidance,
        show_mismatches=show_mismatches,
        show_remediation=show_remediation,
    )


def _print_sync_health_build_result_with_options(
    report_result: SyncHealthBuildResult,
    *,
    show_remediation: bool,
    show_mismatches: bool,
) -> None:
    _print_related_report_details_block(
        title="Related cleanup details:",
        mismatch_warnings=report_result.related_cleanup_mismatch_warnings,
        policy_drift_warnings=report_result.related_cleanup_policy_drift_warnings,
        remediation=report_result.related_cleanup_policy_drift_guidance,
        show_mismatches=show_mismatches,
        show_remediation=show_remediation,
    )
    _print_related_report_details_block(
        title="Related sync audit details:",
        mismatch_warnings=report_result.related_sync_audit_mismatch_warnings,
        policy_drift_warnings=report_result.related_sync_audit_policy_drift_warnings,
        remediation=report_result.related_sync_audit_policy_drift_guidance,
        show_mismatches=show_mismatches,
        show_remediation=show_remediation,
    )


def _print_sync_health_related_report_details(
    snapshot: dict[str, object],
    *,
    show_remediation: bool,
    show_mismatches: bool,
) -> None:
    related_reports = snapshot.get("related_reports")
    if not isinstance(related_reports, dict):
        return
    cleanup_reports = related_reports.get("cleanup_reports")
    if isinstance(cleanup_reports, dict):
        _print_related_report_details_block(
            title="Related cleanup details:",
            mismatch_warnings=extract_related_report_warning_lines(cleanup_reports.get("mismatches")),
            policy_drift_warnings=extract_related_report_warning_lines(
                cleanup_reports.get("policy_drifts")
            ),
            remediation=cleanup_reports.get("policy_drift_guidance")
            if isinstance(cleanup_reports.get("policy_drift_guidance"), str)
            else None,
            show_mismatches=show_mismatches,
            show_remediation=show_remediation,
        )
    sync_audit_reports = related_reports.get("sync_audit_reports")
    if isinstance(sync_audit_reports, dict):
        _print_related_report_details_block(
            title="Related sync audit details:",
            mismatch_warnings=extract_related_report_warning_lines(sync_audit_reports.get("mismatches")),
            policy_drift_warnings=extract_related_report_warning_lines(
                sync_audit_reports.get("policy_drifts")
            ),
            remediation=sync_audit_reports.get("policy_drift_guidance")
            if isinstance(sync_audit_reports.get("policy_drift_guidance"), str)
            else None,
            show_mismatches=show_mismatches,
            show_remediation=show_remediation,
        )


def _print_related_report_details_block(
    *,
    title: str,
    mismatch_warnings: tuple[str, ...],
    policy_drift_warnings: tuple[str, ...],
    remediation: str | None,
    show_mismatches: bool,
    show_remediation: bool,
) -> None:
    for line in _build_related_report_details_lines(
        title=title,
        mismatch_warnings=mismatch_warnings,
        policy_drift_warnings=policy_drift_warnings,
        remediation=remediation,
        show_mismatches=show_mismatches,
        show_remediation=show_remediation,
    ):
        typer.echo(line)


def _build_related_report_details_lines(
    *,
    title: str,
    mismatch_warnings: tuple[str, ...],
    policy_drift_warnings: tuple[str, ...],
    remediation: str | None,
    show_mismatches: bool,
    show_remediation: bool,
    prefix: str = "",
) -> tuple[str, ...]:
    visible_mismatches = mismatch_warnings if show_mismatches else ()
    visible_policy_drifts = policy_drift_warnings if show_remediation else ()
    show_guidance = bool(show_remediation and remediation and policy_drift_warnings)
    block = build_related_report_detail_block(
        mismatch_warnings=visible_mismatches,
        policy_drift_warnings=visible_policy_drifts,
        remediation=remediation if show_guidance else None,
    )
    return render_related_report_detail_lines(
        block,
        title=title,
        section_label_style="machine",
        remediation_label_style="machine",
        layout_policy=build_related_report_detail_line_layout("indented_cli", prefix=prefix),
    )


def _print_skipped_single_issue(store: RunStateStore, issue_id: int) -> None:
    record = store.get(issue_id)
    if record is None:
        typer.echo(f"Issue #{issue_id} is not currently runnable.")
        return
    typer.echo(
        f"Issue #{issue_id} is not currently runnable "
        f"(status={record.status.value}, attempts={record.attempts}). Use --force to run it anyway."
    )
    if record.next_retry_at:
        typer.echo(f"  next_retry_at: {record.next_retry_at.isoformat()}")


def _resolve_sync_selection(
    loaded: LoadedConfig,
    *,
    artifact: str | None,
    issue: int | None,
    tracker: str | None,
    action: str | None,
    latest: bool,
) -> SyncArtifact:
    if artifact:
        return resolve_sync_artifact(loaded, artifact, scope="pending")
    artifacts = list_sync_artifacts(
        loaded,
        issue_id=issue,
        tracker=tracker,
        action=action,
        scope="pending",
    )
    if not artifacts:
        raise SyncArtifactLookupError("No pending sync artifacts matched the requested filters.")
    if len(artifacts) > 1 and not latest:
        joined = ", ".join(item.relative_path for item in artifacts[:5])
        raise SyncArtifactLookupError(
            f"Multiple pending sync artifacts matched the requested filters. Pass an explicit artifact path or use --latest. Matches: {joined}"
        )
    return artifacts[0]
