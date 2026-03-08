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

import httpx
import typer
import yaml

from reporepublic import __version__
from reporepublic.cleanup_report import (
    CleanupReportBuildResult,
    build_cleanup_report,
    normalize_cleanup_report_formats,
)
from reporepublic.config import ConfigLoadError, LoadedConfig, load_config, resolve_repo_root
from reporepublic.dashboard import (
    build_dashboard,
    build_report_health_snapshot,
    normalize_dashboard_formats,
)
from reporepublic.logging import configure_logging
from reporepublic.models import RunLifecycle, RunRecord
from reporepublic.models.domain import utc_now
from reporepublic.orchestrator import DryRunPreview, Orchestrator, RunStateStore, load_webhook_payload
from reporepublic.report_policy import build_report_policy_drift_guidance
from reporepublic.sync_audit import (
    build_sync_audit_report,
    normalize_sync_audit_formats,
)
from reporepublic.sync_artifacts import (
    AppliedSyncManifestRepairResult,
    AppliedSyncManifestReport,
    SyncArtifact,
    SyncArtifactLookupError,
    apply_sync_artifact,
    apply_sync_bundle,
    inspect_applied_sync_manifests,
    list_sync_artifacts,
    repair_applied_sync_manifests,
    resolve_sync_artifact,
)
from reporepublic.templates import (
    PRESETS,
    apply_upgrade_plan,
    build_upgrade_plan,
    detect_scaffold_preset,
    extract_managed_block,
    render_agents_block,
    render_managed_file_map,
    scaffold_repository,
)
from reporepublic.utils import (
    ensure_dir,
    is_git_repository,
    list_dirty_working_tree_entries,
    write_json_file,
)
from reporepublic.workspace import CopyWorkspaceManager, WorktreeWorkspaceManager


app = typer.Typer(
    name="republic",
    help="Install an AI maintainer team into any repo.",
    no_args_is_help=True,
)
sync_app = typer.Typer(help="Inspect staged tracker sync artifacts.")
RAW_POLICY_REPORT_EXPORTS = (
    "sync-audit.json",
    "cleanup-preview.json",
    "cleanup-result.json",
)


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


def main() -> None:
    app()


@app.callback()
def callback() -> None:
    """RepoRepublic CLI."""


app.add_typer(sync_app, name="sync")


@app.command("init")
def init_command(
    preset: str | None = typer.Option(
        None,
        "--preset",
        help="Bootstrap preset: python-library, web-app, docs-only, research-project.",
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
    backend: str | None = typer.Option(
        None,
        "--backend",
        help="Default worker backend: codex or mock.",
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
    force: bool = typer.Option(False, "--force", help="Overwrite managed RepoRepublic files."),
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
                "Local modifications were preserved. Re-run with `republic init --upgrade --force` to overwrite drifted managed files."
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
        backend,
    )
    if interactive_mode:
        typer.echo("Interactive RepoRepublic initialization")
        (
            preset_name,
            resolved_tracker_kind,
            target_repo,
            resolved_tracker_path,
            backend_mode,
            resolved_fixture_issues,
        ) = _prompt_init_inputs(
            repo_root=repo_root,
            preset=preset,
            tracker_kind=tracker_kind,
            tracker_repo=tracker_repo,
            tracker_path=tracker_path,
            fixture_issues=fixture_issues,
            backend=backend,
        )
    else:
        preset_name = preset or "python-library"
        resolved_tracker_kind = _normalize_tracker_kind(tracker_kind or "github")
        target_repo = tracker_repo or f"local/{repo_root.name}"
        resolved_tracker_path = tracker_path or (
            "issues" if resolved_tracker_kind == "local_markdown" else "issues.json"
        )
        backend_mode = _normalize_backend_mode(backend or "codex")
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
    _apply_init_config_overrides(
        repo_root=repo_root,
        backend_mode=backend_mode,
    )
    typer.echo(f"Initialized RepoRepublic in {repo_root}")
    if created:
        typer.echo("Created or updated files:")
        for path in created:
            typer.echo(f"- {path.relative_to(repo_root)}")
    else:
        typer.echo("No files changed. Use --force to refresh managed templates.")


@app.command("doctor")
def doctor_command() -> None:
    repo_root = resolve_repo_root(Path.cwd())
    typer.echo(f"Repo root: {repo_root}")

    config_status = None
    try:
        loaded = load_config(repo_root)
        config_status = loaded
        typer.echo(f"Config: OK ({loaded.config_path})")
    except ConfigLoadError as exc:
        typer.echo(f"Config: ERROR\n{exc}", err=True)
        loaded = None

    codex_command = loaded.data.codex.command if loaded else "codex"
    command_path = shutil.which(codex_command)
    if command_path:
        version = _run_version([codex_command, "--version"])
        typer.echo(f"Codex command: OK ({command_path}) {version.strip()}")
    else:
        typer.echo(f"Codex command: MISSING ({codex_command})", err=True)

    diagnostic_checks: list[DiagnosticCheck] = []
    if loaded:
        _print_tracker_status(loaded)
        working_tree = _get_working_tree_status(loaded)
        _print_workspace_status(loaded, working_tree)
        diagnostic_checks = _collect_doctor_checks(loaded)
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

    typer.echo("RepoRepublic orchestrator started. Press Ctrl+C to stop.")
    try:
        asyncio.run(orchestrator.run_forever())
    except KeyboardInterrupt:
        typer.echo("RepoRepublic orchestrator stopped.")


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
) -> None:
    try:
        loaded = load_config(resolve_repo_root(Path.cwd()))
    except ConfigLoadError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    store = RunStateStore(loaded.state_dir / "runs.json")
    if issue is not None:
        record = store.get(issue)
        if record is None:
            typer.echo(f"No run state recorded for issue #{issue}.", err=True)
            raise typer.Exit(code=1)
        records = [record]
    else:
        records = store.all()
    if not records:
        typer.echo("No runs recorded yet.")
        return
    typer.echo(f"Run state: {loaded.state_dir / 'runs.json'}")
    if issue is None:
        counts = Counter(record.status.value for record in records)
        summary = ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
        typer.echo(f"Run summary: {summary}")
    policy_alignment = _collect_report_policy_export_alignment(loaded)
    _print_status_report_health(
        build_report_health_snapshot(loaded=loaded),
        policy_alignment=policy_alignment,
        policy_health=_collect_report_policy_health(
            loaded,
            policy_alignment=policy_alignment,
        ),
    )
    for record in records:
        _print_run_record(record)


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
        help="Write a cleanup report under .ai-republic/reports/.",
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
    artifact: str = typer.Argument(..., help="Relative path under .ai-republic/sync, basename, or absolute path."),
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
        help="Relative path under .ai-republic/sync, basename, or absolute path. Optional when using filters with --latest.",
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
        typer.echo(json.dumps([_serialize_sync_manifest_report(report) for report in reports], indent=2, sort_keys=True))
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
        typer.echo(json.dumps([_serialize_sync_manifest_repair_result(result) for result in results], indent=2, sort_keys=True))
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
        help="Optional export path. Defaults to .ai-republic/reports/sync-audit.<ext>.",
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
            "Upgrade requires an existing RepoRepublic installation. Run `republic init` first.",
            err=True,
        )
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    detected_preset = detect_scaffold_preset(repo_root)
    preset_name = preset or detected_preset
    if not preset_name:
        typer.echo(
            "Could not detect the installed preset. Pass `--preset` explicitly when using `republic init --upgrade`.",
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
    backend: str | None,
) -> bool:
    if interactive is not None:
        return interactive
    return all(value is None for value in (preset, tracker_kind, tracker_repo, tracker_path, fixture_issues, backend))


def _prompt_init_inputs(
    repo_root: Path,
    preset: str | None,
    tracker_kind: str | None,
    tracker_repo: str | None,
    tracker_path: str | None,
    fixture_issues: str | None,
    backend: str | None,
) -> tuple[str, str, str, str | None, str, str | None]:
    preset_name = _prompt_choice(
        "Preset",
        current=preset,
        default="python-library",
        allowed=sorted(PRESETS),
    )
    resolved_tracker_kind = _prompt_choice(
        "Tracker kind",
        current=tracker_kind,
        default="github",
        allowed=["github", "local_file", "local_markdown"],
    )
    if resolved_tracker_kind == "github":
        target_repo = typer.prompt(
            "Tracker repo",
            default=tracker_repo or f"local/{repo_root.name}",
        ).strip()
        resolved_tracker_path = tracker_path
    else:
        target_repo = tracker_repo or f"local/{repo_root.name}"
        resolved_tracker_path = typer.prompt(
            "Tracker path",
            default=tracker_path or ("issues" if resolved_tracker_kind == "local_markdown" else "issues.json"),
        ).strip()
    backend_mode = _prompt_choice(
        "Backend mode",
        current=backend,
        default="codex",
        allowed=["codex", "mock"],
    )
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
        backend_mode,
        fixture_path,
    )


def _prompt_choice(
    label: str,
    *,
    current: str | None,
    default: str,
    allowed: list[str],
) -> str:
    chosen = typer.prompt(
        f"{label} [{'/'.join(allowed)}]",
        default=current or default,
    ).strip()
    normalized = chosen.strip()
    if normalized not in allowed:
        typer.echo(
            f"Invalid {label.lower()} '{normalized}'. Expected one of: {', '.join(allowed)}.",
            err=True,
        )
        raise typer.Exit(code=2)
    return normalized


def _normalize_backend_mode(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"codex", "mock"}:
        typer.echo(
            f"Invalid backend '{value}'. Expected one of: codex, mock.",
            err=True,
        )
        raise typer.Exit(code=2)
    return normalized


def _normalize_tracker_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"github", "local_file", "local_markdown"}:
        typer.echo(
            f"Invalid tracker kind '{value}'. Expected one of: github, local_file, local_markdown.",
            err=True,
        )
        raise typer.Exit(code=2)
    return normalized


def _apply_init_config_overrides(
    repo_root: Path,
    *,
    backend_mode: str,
) -> None:
    if backend_mode == "codex":
        return
    config_path = repo_root / ".ai-republic" / "reporepublic.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    payload.setdefault("llm", {})["mode"] = backend_mode
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


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
            gh_present = bool(shutil.which("gh"))
            typer.echo(
                "GitHub auth: "
                + (
                    "token available or gh installed"
                    if token_present or gh_present
                    else f"set {tracker.token_env} for live API access"
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
    required = [
        loaded.ai_root / "reporepublic.yaml",
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
        loaded.repo_root / ".github" / "workflows" / "republic-check.yml",
    ]
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


def _collect_doctor_checks(loaded: LoadedConfig) -> list[DiagnosticCheck]:
    policy_alignment = _collect_report_policy_export_alignment(loaded)
    checks: list[DiagnosticCheck]
    if loaded.data.tracker.kind.value == "github":
        checks = [
            _probe_github_auth(loaded),
            _probe_github_network(loaded),
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


def _probe_github_auth(loaded: LoadedConfig) -> DiagnosticCheck:
    if loaded.data.tracker.mode.value == "fixture":
        return DiagnosticCheck(
            name="GitHub auth",
            status="NOT_APPLICABLE",
            message="fixture tracker mode does not require live GitHub authentication",
        )
    token_env = loaded.data.tracker.token_env
    if os.getenv(token_env):
        return DiagnosticCheck(
            name="GitHub auth",
            status="OK",
            message=f"{token_env} is set",
        )
    gh_path = shutil.which("gh")
    if gh_path:
        completed = subprocess.run(
            ["gh", "auth", "status", "--hostname", "github.com"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        if completed.returncode == 0:
            return DiagnosticCheck(
                name="GitHub auth",
                status="OK",
                message=f"gh auth is available via {gh_path}",
            )
        return DiagnosticCheck(
            name="GitHub auth",
            status="WARN",
            message="gh is installed but not authenticated",
            hint=f"Run `gh auth login` or set {token_env}.",
        )
    return DiagnosticCheck(
        name="GitHub auth",
        status="WARN",
        message=f"{token_env} is not set",
        hint=f"Set {token_env} or install/authenticate `gh` for live API access.",
    )


def _probe_github_network(loaded: LoadedConfig) -> DiagnosticCheck:
    if loaded.data.tracker.mode.value == "fixture":
        return DiagnosticCheck(
            name="GitHub network",
            status="NOT_APPLICABLE",
            message="fixture tracker mode does not contact the GitHub API",
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
            probe_path = path / ".reporepublic-write-check"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{label}={path} ({exc})")
    if failures:
        return DiagnosticCheck(
            name="Write permissions",
            status="ERROR",
            message="one or more RepoRepublic directories are not writable",
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
            hint="Run `republic init --upgrade` to inspect managed scaffold drift, or pass `--preset` explicitly.",
        )

    expected_files = render_managed_file_map(
        preset_name=preset_name,
        tracker_repo=loaded.data.tracker.repo or f"local/{loaded.repo_root.name}",
        fixture_issues=loaded.data.tracker.fixtures_path,
        tracker_kind=loaded.data.tracker.kind.value,
        tracker_path=loaded.data.tracker.path,
    )
    drifted: list[str] = []
    ignored = {Path(".ai-republic/reporepublic.yaml")}
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
            hint="Review local changes or run `republic init --upgrade` to inspect drift. "
            + "Use `republic init --upgrade --force` to refresh managed files. "
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
    if not visible_mismatches and not visible_policy_drifts and not show_guidance:
        return ()
    lines: list[str] = [f"{prefix}{title}"]
    section_prefix = f"{prefix}  "
    item_prefix = f"{prefix}    "
    if visible_mismatches:
        lines.append(f"{section_prefix}mismatches:")
        for warning in visible_mismatches:
            lines.append(f"{item_prefix}- {warning}")
    if visible_policy_drifts:
        lines.append(f"{section_prefix}policy_drifts:")
        for warning in visible_policy_drifts:
            lines.append(f"{item_prefix}- {warning}")
    if show_guidance:
        lines.append(f"{section_prefix}remediation: {remediation}")
    return tuple(lines)


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


def _serialize_sync_manifest_report(report: AppliedSyncManifestReport) -> dict[str, object]:
    return {
        "tracker": report.tracker,
        "issue_id": report.issue_id,
        "issue_root": str(report.issue_root),
        "manifest_path": str(report.manifest_path),
        "manifest_exists": report.manifest_exists,
        "manifest_entry_count": report.manifest_entry_count,
        "referenced_archive_count": report.referenced_archive_count,
        "archive_files": list(report.archive_files),
        "findings": [
            {
                "code": finding.code,
                "message": finding.message,
                "entry_key": finding.entry_key,
                "path": finding.path,
            }
            for finding in report.findings
        ],
    }


def _serialize_sync_manifest_repair_result(result: AppliedSyncManifestRepairResult) -> dict[str, object]:
    return {
        "tracker": result.tracker,
        "issue_id": result.issue_id,
        "issue_root": str(result.issue_root),
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
