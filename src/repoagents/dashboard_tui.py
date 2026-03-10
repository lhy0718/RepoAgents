from __future__ import annotations

import asyncio
import sys
import textwrap
import time
from dataclasses import dataclass, field
import importlib
from typing import Any

from repoagents.cleanup_report import build_cleanup_report
from repoagents.config import LoadedConfig
from repoagents.dashboard import build_dashboard_snapshot
from repoagents.github_health import build_github_smoke_exports, build_github_smoke_snapshot
from repoagents.models import RunLifecycle
from repoagents.ops_status import build_ops_status_exports, build_ops_status_snapshot
from repoagents.orchestrator import RunStateStore
from repoagents.sync_audit import build_sync_audit_report
from repoagents.sync_health import build_sync_health_report
from repoagents.tracker import build_tracker

try:
    import curses
except ImportError:  # pragma: no cover - platform-specific import
    curses = None


SECTION_SPECS = (
    ("runs", "Runs"),
    ("reports", "Reports"),
    ("ops", "Ops"),
    ("handoffs", "Handoffs"),
    ("retention", "Retention"),
)
KEY_SHIFT_TAB = 353


@dataclass(frozen=True, slots=True)
class DashboardTuiAction:
    key: str
    label: str
    confirmation_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class DashboardTuiEntry:
    title: str
    subtitle: str
    status: str
    details: tuple[str, ...]
    actions: tuple[DashboardTuiAction, ...] = ()
    context: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DashboardTuiSection:
    key: str
    label: str
    entries: tuple[DashboardTuiEntry, ...]


@dataclass(frozen=True, slots=True)
class DashboardTuiModel:
    title: str
    subtitle: str
    summary_lines: tuple[str, ...]
    sections: tuple[DashboardTuiSection, ...]


def run_dashboard_tui(
    loaded: LoadedConfig,
    *,
    limit: int,
    refresh_seconds: int,
) -> None:
    if curses is None:  # pragma: no cover - platform-specific branch
        raise RuntimeError("dashboard TUI is not available on this platform.")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("`repoagents dashboard --tui` requires an interactive terminal.")

    def runner(stdscr: Any) -> None:
        _dashboard_tui_main(
            stdscr,
            loaded=loaded,
            limit=limit,
            refresh_seconds=refresh_seconds,
        )

    curses.wrapper(runner)


def load_dashboard_tui_model(
    loaded: LoadedConfig,
    *,
    limit: int,
    refresh_seconds: int,
) -> DashboardTuiModel:
    store = RunStateStore(loaded.state_dir / "runs.json")
    all_records = store.all()
    visible_records = all_records[:limit]
    snapshot = build_dashboard_snapshot(
        loaded=loaded,
        all_records=all_records,
        visible_records=visible_records,
        output_path=loaded.ai_root / "dashboard" / "index.md",
        refresh_seconds=refresh_seconds,
        sync_limit=limit,
    )
    return build_dashboard_tui_model(snapshot)


def build_dashboard_tui_model(snapshot: dict[str, object]) -> DashboardTuiModel:
    meta = _mapping(snapshot.get("meta"))
    hero = _mapping(snapshot.get("hero"))
    counts = _mapping(snapshot.get("counts"))
    reports = _mapping(snapshot.get("reports"))
    retention = _mapping(snapshot.get("sync_retention"))
    ops = _mapping(snapshot.get("ops_snapshots"))

    title = f"RepoAgents TUI | {meta.get('repo_name', 'repo')}"
    subtitle = (
        f"{hero.get('title', 'Dashboard summary')} "
        f"[{hero.get('severity', 'clean')}] | rendered {meta.get('rendered_at', 'n/a')}"
    )
    summary_lines = (
        str(hero.get("summary") or "No summary available."),
        (
            f"Runs {counts.get('visible_runs', 0)}/{counts.get('total_runs', 0)} | "
            f"Reports {reports.get('total', 0)} | "
            f"Handoffs {counts.get('visible_sync_handoffs', 0)} | "
            f"Retention issues {retention.get('total_issues', 0)}"
        ),
        (
            f"Ops history {ops.get('history_entry_count', 0)} | "
            f"Ops archives {ops.get('archive_entry_count', 0)} | "
            f"Policy drift reports {counts.get('policy_drift_reports', 0)} | "
            f"Last updated {meta.get('last_updated', 'n/a')}"
        ),
    )
    return DashboardTuiModel(
        title=title,
        subtitle=subtitle,
        summary_lines=summary_lines,
        sections=(
            _build_runs_section(snapshot),
            _build_reports_section(snapshot),
            _build_ops_section(snapshot),
            _build_handoffs_section(snapshot),
            _build_retention_section(snapshot),
        ),
    )


def _build_runs_section(snapshot: dict[str, object]) -> DashboardTuiSection:
    entries = []
    for run in _list_of_dicts(snapshot.get("runs")):
        issue_id = run.get("issue_id", "?")
        issue_title = run.get("issue_title", "Untitled issue")
        details = [
            f"run_id: {run.get('run_id', 'n/a')}",
            f"backend: {run.get('backend_mode', 'n/a')}",
            f"updated_at: {run.get('updated_at', 'n/a')}",
        ]
        current_role = _string(run.get("current_role"))
        if current_role:
            details.append(f"current_role: {current_role}")
        summary = _string(run.get("summary"))
        if summary:
            details.append(f"summary: {summary}")
        last_error = _string(run.get("last_error"))
        if last_error:
            details.append(f"last_error: {last_error}")
        workspace_path = _string(run.get("workspace_path"))
        if workspace_path:
            details.append(f"workspace: {workspace_path}")
        artifacts = _list_of_dicts(run.get("artifacts"))
        if artifacts:
            labels = ", ".join(str(item.get("label", "artifact")) for item in artifacts[:6])
            details.append(f"artifacts: {labels}")
        external_actions = _list_of_dicts(run.get("external_actions"))
        if external_actions:
            labels = ", ".join(str(item.get("action", "action")) for item in external_actions[:6])
            details.append(f"external_actions: {labels}")
        actions: tuple[DashboardTuiAction, ...] = ()
        if isinstance(issue_id, int) and str(run.get("status", "unknown")) != RunLifecycle.IN_PROGRESS.value:
            actions = (
                DashboardTuiAction(
                    key="retry_issue",
                    label=f"Retry issue #{issue_id}",
                    confirmation_prompt=f"Schedule issue #{issue_id} for immediate retry? [y/N]",
                ),
            )
        entries.append(
            DashboardTuiEntry(
                title=f"#{issue_id} {issue_title}",
                subtitle=f"{run.get('status', 'unknown')} | attempts={run.get('attempts', 0)}",
                status=str(run.get("status", "unknown")),
                details=tuple(details),
                actions=actions,
                context={
                    "issue_id": issue_id,
                    "run_id": run.get("run_id"),
                    "run_status": run.get("status"),
                },
            )
        )
    return DashboardTuiSection(key="runs", label="Runs", entries=tuple(entries))


def _build_reports_section(snapshot: dict[str, object]) -> DashboardTuiSection:
    reports = _mapping(snapshot.get("reports"))
    entries = []
    for report in _list_of_dicts(reports.get("entries")):
        report_key = _string(report.get("key"))
        label = str(report.get("label", "Report"))
        details = [
            f"summary: {report.get('summary', 'n/a')}",
            f"freshness: {report.get('freshness_status', 'unknown')}",
            f"age: {report.get('age_human', 'n/a')}",
        ]
        policy_note = _string(report.get("policy_alignment_note"))
        if policy_note:
            details.append(f"policy: {policy_note}")
        detail_summary = _string(report.get("related_report_detail_summary"))
        if detail_summary:
            details.append(f"related: {detail_summary}")
        metrics = _mapping(report.get("metrics"))
        if metrics:
            metric_bits = [
                f"{key}={value}"
                for key, value in list(metrics.items())[:6]
            ]
            details.append("metrics: " + ", ".join(metric_bits))
        json_path = _string(report.get("json_path"))
        if json_path:
            details.append(f"json: {json_path}")
        markdown_path = _string(report.get("markdown_path"))
        if markdown_path:
            details.append(f"markdown: {markdown_path}")
        actions = _build_report_actions(report_key=report_key, label=label)
        entries.append(
            DashboardTuiEntry(
                title=label,
                subtitle=(
                    f"{report.get('status', 'available')} | "
                    f"{report.get('freshness_status', 'unknown')} | age={report.get('age_human', 'n/a')}"
                ),
                status=str(report.get("status", "available")),
                details=tuple(details),
                actions=actions,
                context={"report_key": report_key, "label": label},
            )
        )
    return DashboardTuiSection(key="reports", label="Reports", entries=tuple(entries))


def _build_report_actions(
    *,
    report_key: str | None,
    label: str,
) -> tuple[DashboardTuiAction, ...]:
    if report_key in {"sync-audit", "sync-health", "github-smoke", "cleanup-preview", "ops-status"}:
        return (
            DashboardTuiAction(
                key="refresh_report",
                label=f"Refresh {label}",
            ),
        )
    return ()


def _build_ops_section(snapshot: dict[str, object]) -> DashboardTuiSection:
    ops = _mapping(snapshot.get("ops_snapshots"))
    entries = []
    latest = _mapping(ops.get("latest"))
    if latest:
        entries.append(_ops_entry_from_payload("Latest", latest))
    latest_id = _string(latest.get("entry_id"))
    for entry in _list_of_dicts(ops.get("entries")):
        if latest_id and _string(entry.get("entry_id")) == latest_id:
            continue
        entries.append(_ops_entry_from_payload("History", entry))
    return DashboardTuiSection(key="ops", label="Ops", entries=tuple(entries))


def _ops_entry_from_payload(prefix: str, payload: dict[str, object]) -> DashboardTuiEntry:
    component_statuses = _mapping(payload.get("component_statuses"))
    component_bits = ", ".join(
        f"{key}={value}" for key, value in list(component_statuses.items())[:6]
    )
    details = [
        f"headline: {payload.get('brief_headline', 'n/a')}",
        f"overall: {payload.get('overall_status', 'unknown')}",
        f"brief: {payload.get('brief_severity', 'unknown')}",
        f"age: {payload.get('age_human', 'n/a')}",
        f"bundle_dir: {payload.get('bundle_dir', 'n/a')}",
    ]
    if component_bits:
        details.append(f"components: {component_bits}")
    archive_path = _string(payload.get("archive_path"))
    if archive_path:
        details.append(f"archive: {archive_path}")
    return DashboardTuiEntry(
        title=f"{prefix} {payload.get('entry_id', 'n/a')}",
        subtitle=(
            f"{payload.get('overall_status', 'unknown')} | "
            f"brief={payload.get('brief_severity', 'unknown')} | age={payload.get('age_human', 'n/a')}"
        ),
        status=str(payload.get("overall_status", "unknown")),
        details=tuple(details),
    )


def _build_handoffs_section(snapshot: dict[str, object]) -> DashboardTuiSection:
    entries = []
    for handoff in _list_of_dicts(snapshot.get("sync_handoffs")):
        details = [
            f"summary: {handoff.get('summary', 'n/a')}",
            f"tracker: {handoff.get('tracker', 'n/a')}",
            f"applied_at: {handoff.get('applied_at', 'n/a')}",
            f"artifact_role: {handoff.get('artifact_role', 'n/a')}",
            f"bundle_key: {handoff.get('bundle_key', 'n/a')}",
        ]
        archived_path = _string(handoff.get("archived_path"))
        if archived_path:
            details.append(f"archived: {archived_path}")
        manifest_path = _string(handoff.get("manifest_path"))
        if manifest_path:
            details.append(f"manifest: {manifest_path}")
        entries.append(
            DashboardTuiEntry(
                title=f"#{handoff.get('issue_id', '?')} {handoff.get('action', 'handoff')}",
                subtitle=(
                    f"{handoff.get('tracker', 'tracker')} | "
                    f"role={handoff.get('artifact_role', 'n/a')} | "
                    f"{handoff.get('staged_at', 'n/a')}"
                ),
                status=str(handoff.get("action", "handoff")),
                details=tuple(details),
            )
        )
    return DashboardTuiSection(key="handoffs", label="Handoffs", entries=tuple(entries))


def _build_retention_section(snapshot: dict[str, object]) -> DashboardTuiSection:
    retention = _mapping(snapshot.get("sync_retention"))
    entries = []
    for entry in _list_of_dicts(retention.get("entries")):
        groups = _list_of_dicts(entry.get("groups"))
        details = [
            f"status: {entry.get('status', 'n/a')}",
            f"keep_limit: {entry.get('keep_groups_limit', 'n/a')}",
            f"total_groups: {entry.get('total_groups', 0)}",
            f"prunable_groups: {entry.get('prunable_groups', 0)}",
            f"prunable_bytes: {entry.get('prunable_bytes_human', 'n/a')}",
            f"repair_findings: {entry.get('integrity_findings', 0)}",
            f"oldest_prunable_age: {entry.get('oldest_prunable_group_age_human', 'n/a')}",
        ]
        if groups:
            group_bits = ", ".join(
                f"{group.get('status', 'group')}:{group.get('group_key', 'n/a')}"
                for group in groups[:3]
            )
            details.append(f"groups: {group_bits}")
        entries.append(
            DashboardTuiEntry(
                title=f"{entry.get('tracker', 'tracker')} / issue-{entry.get('issue_id', '?')}",
                subtitle=(
                    f"{entry.get('status', 'n/a')} | "
                    f"prunable={entry.get('prunable_groups', 0)} | "
                    f"bytes={entry.get('prunable_bytes_human', 'n/a')}"
                ),
                status=str(entry.get("status", "n/a")),
                details=tuple(details),
            )
        )
    return DashboardTuiSection(key="retention", label="Retention", entries=tuple(entries))


def _dashboard_tui_main(
    stdscr: Any,
    *,
    loaded: LoadedConfig,
    limit: int,
    refresh_seconds: int,
) -> None:
    _configure_curses(stdscr)
    model = load_dashboard_tui_model(loaded, limit=limit, refresh_seconds=refresh_seconds)
    section_index = 0
    selections = [0 for _ in model.sections]
    message = "Press q to quit, r to refresh."
    last_refresh = time.monotonic()
    action_menu: tuple[DashboardTuiAction, ...] | None = None
    pending_confirmation: tuple[DashboardTuiEntry, DashboardTuiAction] | None = None

    while True:
        _draw_dashboard_tui(
            stdscr,
            model=model,
            section_index=section_index,
            selections=selections,
            message=message,
            refresh_seconds=refresh_seconds,
            action_menu=action_menu,
            pending_confirmation=pending_confirmation,
        )
        key = stdscr.getch()
        selected_entry = _selected_entry(model.sections[section_index], selections[section_index])
        if pending_confirmation is not None:
            entry, action = pending_confirmation
            if key in (ord("y"), ord("Y")):
                model, selections, message = _execute_dashboard_tui_action_and_reload(
                    loaded=loaded,
                    model=model,
                    selections=selections,
                    section_key=model.sections[section_index].key,
                    entry=entry,
                    action=action,
                    limit=limit,
                    refresh_seconds=refresh_seconds,
                )
                pending_confirmation = None
                action_menu = None
                last_refresh = time.monotonic()
                continue
            if key in (27, ord("n"), ord("N"), ord("c"), ord("C")):
                pending_confirmation = None
                action_menu = None
                message = "Action cancelled."
                continue
            if key in (ord("q"), ord("Q")):
                return
            continue
        if action_menu is not None:
            if key in (27, ord("c"), ord("C")):
                action_menu = None
                message = "Action menu closed."
                continue
            if key in (ord("q"), ord("Q")):
                return
            if ord("1") <= key <= ord(str(min(len(action_menu), 9))):
                action = action_menu[key - ord("1")]
                if selected_entry is None:
                    action_menu = None
                    message = "No entry selected."
                    continue
                if action.confirmation_prompt:
                    pending_confirmation = (selected_entry, action)
                    message = action.confirmation_prompt
                else:
                    model, selections, message = _execute_dashboard_tui_action_and_reload(
                        loaded=loaded,
                        model=model,
                        selections=selections,
                        section_key=model.sections[section_index].key,
                        entry=selected_entry,
                        action=action,
                        limit=limit,
                        refresh_seconds=refresh_seconds,
                    )
                    action_menu = None
                    last_refresh = time.monotonic()
                continue
            continue
        if key == -1:
            if refresh_seconds > 0 and time.monotonic() - last_refresh >= refresh_seconds:
                model = load_dashboard_tui_model(loaded, limit=limit, refresh_seconds=refresh_seconds)
                selections = _normalize_selections(model, selections)
                message = f"Refreshed at {time.strftime('%H:%M:%S')}."
                last_refresh = time.monotonic()
            continue
        if key in (ord("q"), ord("Q")):
            return
        if key in (ord("r"), ord("R")):
            model = load_dashboard_tui_model(loaded, limit=limit, refresh_seconds=refresh_seconds)
            selections = _normalize_selections(model, selections)
            message = f"Refreshed at {time.strftime('%H:%M:%S')}."
            last_refresh = time.monotonic()
            continue
        if key in (ord("a"), ord("A")):
            if selected_entry is None:
                message = "No entry selected."
            elif not selected_entry.actions:
                message = "No actions available for the selected entry."
            else:
                action_menu = selected_entry.actions
                message = f"Actions for {selected_entry.title}."
            continue
        if key in (curses.KEY_RIGHT, ord("\t")):
            section_index = (section_index + 1) % len(model.sections)
            continue
        if key in (curses.KEY_LEFT, KEY_SHIFT_TAB):
            section_index = (section_index - 1) % len(model.sections)
            continue
        if key == curses.KEY_DOWN:
            entries = model.sections[section_index].entries
            if entries:
                selections[section_index] = min(selections[section_index] + 1, len(entries) - 1)
            continue
        if key == curses.KEY_UP:
            entries = model.sections[section_index].entries
            if entries:
                selections[section_index] = max(selections[section_index] - 1, 0)
            continue
        if ord("1") <= key <= ord(str(min(len(model.sections), 9))):
            section_index = key - ord("1")


def _configure_curses(stdscr: Any) -> None:
    stdscr.keypad(True)
    stdscr.timeout(250)
    try:
        curses.curs_set(0)
    except curses.error:  # pragma: no cover - terminal-specific
        pass
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_RED, -1)


def _draw_dashboard_tui(
    stdscr: Any,
    *,
    model: DashboardTuiModel,
    section_index: int,
    selections: list[int],
    message: str,
    refresh_seconds: int,
    action_menu: tuple[DashboardTuiAction, ...] | None,
    pending_confirmation: tuple[DashboardTuiEntry, DashboardTuiAction] | None,
) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    if height < 18 or width < 72:
        _safe_addstr(stdscr, 0, 0, "Terminal too small for RepoAgents dashboard TUI.")
        _safe_addstr(stdscr, 1, 0, f"Current size: {width}x{height}. Resize to at least 72x18.")
        _safe_addstr(stdscr, 3, 0, "Press q to quit.")
        stdscr.refresh()
        return

    y = 0
    _safe_addstr(stdscr, y, 0, model.title, curses.A_BOLD | _color_attr("accent"))
    y += 1
    _safe_addstr(stdscr, y, 0, model.subtitle, _color_attr("muted"))
    y += 1
    for line in model.summary_lines:
        _safe_addstr(stdscr, y, 0, line, 0)
        y += 1
    y += 1
    _draw_tabs(stdscr, y, model.sections, section_index, width)
    y += 2

    footer_y = height - 2
    content_height = footer_y - y
    if width < 112 or content_height < 12:
        list_height = max(5, content_height // 2)
        _draw_section_list(
            stdscr,
            y=y,
            x=0,
            width=width,
            height=list_height,
            section=model.sections[section_index],
            selected_index=selections[section_index],
        )
        divider_y = y + list_height
        if divider_y < footer_y:
            try:
                stdscr.hline(divider_y, 0, "-", width)
            except curses.error:
                pass
        _draw_entry_details(
            stdscr,
            y=divider_y + 1,
            x=0,
            width=width,
            height=footer_y - divider_y - 1,
            entry=_selected_entry(model.sections[section_index], selections[section_index]),
        )
    else:
        list_width = max(36, width // 3)
        _draw_section_list(
            stdscr,
            y=y,
            x=0,
            width=list_width,
            height=content_height,
            section=model.sections[section_index],
            selected_index=selections[section_index],
        )
        try:
            stdscr.vline(y, list_width, "|", content_height)
        except curses.error:
            pass
        _draw_entry_details(
            stdscr,
            y=y,
            x=list_width + 2,
            width=width - list_width - 2,
            height=content_height,
            entry=_selected_entry(model.sections[section_index], selections[section_index]),
        )

    refresh_note = (
        f"auto-refresh {refresh_seconds}s"
        if refresh_seconds > 0
        else "manual refresh"
    )
    if pending_confirmation is not None:
        footer = f"Confirm: y execute | n cancel | q quit | {refresh_note}"
        message_line = pending_confirmation[1].confirmation_prompt or message
    elif action_menu is not None:
        action_bits = " | ".join(
            f"[{index + 1}] {action.label}" for index, action in enumerate(action_menu[:9])
        )
        footer = f"Actions: {action_bits} | Esc cancel | q quit"
        message_line = message
    else:
        footer = (
            "Keys: 1-5 switch | Tab/Left/Right change section | Up/Down move | "
            f"a actions | r refresh | q quit | {refresh_note}"
        )
        message_line = message
    _safe_addstr(stdscr, footer_y, 0, footer, _color_attr("muted"))
    _safe_addstr(stdscr, footer_y + 1, 0, message_line, _color_attr("muted"))
    stdscr.refresh()


def _draw_tabs(
    stdscr: Any,
    y: int,
    sections: tuple[DashboardTuiSection, ...],
    section_index: int,
    width: int,
) -> None:
    x = 0
    for idx, section in enumerate(sections):
        label = f"[{idx + 1}] {section.label}"
        attr = curses.A_BOLD if idx == section_index else 0
        if idx == section_index:
            attr |= curses.A_REVERSE
        _safe_addstr(stdscr, y, x, label, attr)
        x += len(label) + 2
        if x >= width:
            break


def _draw_section_list(
    stdscr: Any,
    *,
    y: int,
    x: int,
    width: int,
    height: int,
    section: DashboardTuiSection,
    selected_index: int,
) -> None:
    _safe_addstr(
        stdscr,
        y,
        x,
        f"{section.label} ({len(section.entries)})",
        curses.A_BOLD | _color_attr("accent"),
    )
    if height <= 1:
        return
    if not section.entries:
        _safe_addstr(stdscr, y + 1, x, "No entries yet.", _color_attr("muted"))
        return
    available_rows = max(1, height - 1)
    start = 0
    if selected_index >= available_rows:
        start = selected_index - available_rows + 1
    visible_entries = section.entries[start : start + available_rows]
    for offset, entry in enumerate(visible_entries, start=1):
        actual_index = start + offset - 1
        row_y = y + offset
        marker = ">" if actual_index == selected_index else " "
        attr = curses.A_BOLD if actual_index == selected_index else 0
        if actual_index == selected_index:
            attr |= curses.A_REVERSE
        status_tag = _status_tag(entry.status)
        line = f"{marker} {status_tag:<5} {entry.title}"
        _safe_addstr(stdscr, row_y, x, line, attr | _status_attr(entry.status))


def _draw_entry_details(
    stdscr: Any,
    *,
    y: int,
    x: int,
    width: int,
    height: int,
    entry: DashboardTuiEntry | None,
) -> None:
    if height <= 0 or width <= 0:
        return
    if entry is None:
        _safe_addstr(stdscr, y, x, "No entry selected.", _color_attr("muted"))
        return
    current_y = y
    _safe_addstr(stdscr, current_y, x, entry.title, curses.A_BOLD | _status_attr(entry.status))
    current_y += 1
    _safe_addstr(stdscr, current_y, x, entry.subtitle, _color_attr("muted"))
    current_y += 2
    for detail in entry.details:
        for wrapped in textwrap.wrap(detail, width=max(12, width - 1)) or [""]:
            if current_y >= y + height:
                return
            _safe_addstr(stdscr, current_y, x, wrapped, 0)
            current_y += 1
    if entry.actions and current_y < y + height:
        current_y += 1
        if current_y < y + height:
            labels = ", ".join(action.label for action in entry.actions)
            _safe_addstr(stdscr, current_y, x, f"Actions: {labels}", curses.A_BOLD | _color_attr("accent"))


def execute_dashboard_tui_action(
    loaded: LoadedConfig,
    *,
    section_key: str,
    entry: DashboardTuiEntry,
    action: DashboardTuiAction,
    limit: int,
) -> str:
    if section_key == "runs" and action.key == "retry_issue":
        issue_id = entry.context.get("issue_id")
        if not isinstance(issue_id, int):
            raise RuntimeError("Selected run does not expose a valid issue id.")
        store = RunStateStore(loaded.state_dir / "runs.json")
        record = store.get(issue_id)
        if record is None:
            raise RuntimeError(f"Issue #{issue_id} no longer has a stored run record.")
        if record.status == RunLifecycle.IN_PROGRESS:
            raise RuntimeError(f"Issue #{issue_id} is still in progress and cannot be retried yet.")
        updated = store.force_retry(issue_id, "Manual retry requested from dashboard TUI.")
        if updated is None:
            raise RuntimeError(f"Unable to schedule retry for issue #{issue_id}.")
        return f"Issue #{issue_id} scheduled for immediate retry."

    if section_key == "reports" and action.key == "refresh_report":
        report_key = entry.context.get("report_key")
        if not isinstance(report_key, str) or not report_key:
            raise RuntimeError("Selected report is missing its report key.")
        return _refresh_dashboard_report(loaded=loaded, report_key=report_key, limit=limit)

    raise RuntimeError(f"Unsupported dashboard action '{action.key}' for section '{section_key}'.")


def _execute_dashboard_tui_action_and_reload(
    *,
    loaded: LoadedConfig,
    model: DashboardTuiModel,
    selections: list[int],
    section_key: str,
    entry: DashboardTuiEntry,
    action: DashboardTuiAction,
    limit: int,
    refresh_seconds: int,
) -> tuple[DashboardTuiModel, list[int], str]:
    try:
        message = execute_dashboard_tui_action(
            loaded,
            section_key=section_key,
            entry=entry,
            action=action,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        return model, selections, f"Action failed: {exc}"

    refreshed_model = load_dashboard_tui_model(
        loaded,
        limit=limit,
        refresh_seconds=refresh_seconds,
    )
    return refreshed_model, _normalize_selections(refreshed_model, selections), message


def _refresh_dashboard_report(
    *,
    loaded: LoadedConfig,
    report_key: str,
    limit: int,
) -> str:
    if report_key == "sync-audit":
        build_sync_audit_report(
            loaded,
            output_path=loaded.reports_dir / "sync-audit.json",
            formats=("json", "markdown"),
            limit=limit,
        )
        return "Refreshed Sync audit report."

    if report_key == "sync-health":
        records = RunStateStore(loaded.state_dir / "runs.json").all()
        cleanup_keep_groups = loaded.data.cleanup.sync_applied_keep_groups_per_issue
        cleanup_actions = _collect_dashboard_clean_actions(
            loaded=loaded,
            records=records,
            sync_keep_groups_per_issue=cleanup_keep_groups,
        )
        build_sync_health_report(
            loaded,
            cleanup_actions=cleanup_actions,
            limit=limit,
            cleanup_include_sync_applied=True,
            cleanup_keep_groups_per_issue=cleanup_keep_groups,
            output_path=loaded.reports_dir / "sync-health.json",
            formats=("json", "markdown"),
        )
        return "Refreshed Sync health report."

    if report_key == "cleanup-preview":
        records = RunStateStore(loaded.state_dir / "runs.json").all()
        cleanup_keep_groups = loaded.data.cleanup.sync_applied_keep_groups_per_issue
        cleanup_actions = _collect_dashboard_clean_actions(
            loaded=loaded,
            records=records,
            sync_keep_groups_per_issue=cleanup_keep_groups,
        )
        build_cleanup_report(
            loaded,
            actions=cleanup_actions,
            dry_run=True,
            include_sync_applied=True,
            issue_id=None,
            sync_keep_groups_per_issue=cleanup_keep_groups,
            output_path=loaded.reports_dir / "cleanup-preview.json",
            formats=("json", "markdown"),
        )
        return "Refreshed Cleanup preview report."

    if report_key == "ops-status":
        snapshot = build_ops_status_snapshot(loaded=loaded)
        build_ops_status_exports(
            snapshot=snapshot,
            output_path=loaded.reports_dir / "ops-status.json",
            formats=("json", "markdown"),
        )
        return "Refreshed Ops status report."

    if report_key == "github-smoke":
        if loaded.data.tracker.kind.value != "github" or loaded.data.tracker.mode.value != "rest":
            raise RuntimeError("GitHub smoke refresh requires tracker.kind=github and tracker.mode=rest.")
        tracker = build_tracker(loaded, dry_run=False)
        snapshot = asyncio.run(
            _collect_dashboard_github_smoke_snapshot(
                loaded=loaded,
                tracker=tracker,
                issue_limit=min(max(limit, 1), 50),
            )
        )
        build_github_smoke_exports(
            snapshot=snapshot,
            output_path=loaded.reports_dir / "github-smoke.json",
            formats=("json", "markdown"),
        )
        return "Refreshed GitHub smoke report."

    raise RuntimeError(f"Direct refresh is not available for report '{report_key}' yet.")


def _collect_dashboard_clean_actions(
    *,
    loaded: LoadedConfig,
    records: list[object],
    sync_keep_groups_per_issue: int,
) -> list[object]:
    app_module = importlib.import_module("repoagents.cli.app")
    return app_module._collect_clean_actions(
        loaded,
        records,
        include_sync_applied=True,
        sync_keep_groups_per_issue=sync_keep_groups_per_issue,
    )


async def _collect_dashboard_github_smoke_snapshot(
    *,
    loaded: LoadedConfig,
    tracker: Any,
    issue_limit: int,
) -> dict[str, object]:
    try:
        return await build_github_smoke_snapshot(
            loaded=loaded,
            tracker=tracker,
            issue_id=None,
            issue_limit=issue_limit,
        )
    finally:
        await tracker.aclose()


def _selected_entry(section: DashboardTuiSection, selected_index: int) -> DashboardTuiEntry | None:
    if not section.entries:
        return None
    index = min(max(selected_index, 0), len(section.entries) - 1)
    return section.entries[index]


def _normalize_selections(model: DashboardTuiModel, selections: list[int]) -> list[int]:
    normalized = list(selections[: len(model.sections)])
    while len(normalized) < len(model.sections):
        normalized.append(0)
    for idx, section in enumerate(model.sections):
        if not section.entries:
            normalized[idx] = 0
        else:
            normalized[idx] = min(max(normalized[idx], 0), len(section.entries) - 1)
    return normalized


def _safe_addstr(stdscr: Any, y: int, x: int, text: str, attr: int = 0) -> None:
    if y < 0 or x < 0:
        return
    try:
        max_y, max_x = stdscr.getmaxyx()
    except Exception:  # noqa: BLE001
        return
    if y >= max_y or x >= max_x:
        return
    clipped = text[: max(0, max_x - x - 1)]
    if not clipped:
        return
    try:
        stdscr.addstr(y, x, clipped, attr)
    except Exception:  # noqa: BLE001
        return


def _color_attr(name: str) -> int:
    if curses is None:  # pragma: no cover - terminal-specific
        return 0
    try:
        if not curses.has_colors():
            return 0
    except curses.error:  # pragma: no cover - terminal-specific
        return 0
    pair = {
        "accent": 1,
        "clean": 2,
        "attention": 3,
        "issues": 4,
        "muted": 1,
    }.get(name)
    return curses.color_pair(pair) if pair else 0


def _status_attr(status: str) -> int:
    normalized = status.lower()
    if normalized in {"completed", "ok", "clean", "available"}:
        return _color_attr("clean")
    if normalized in {"failed", "issues", "error"}:
        return _color_attr("issues")
    if normalized in {"attention", "warn", "retry_pending"}:
        return _color_attr("attention")
    return 0


def _status_tag(status: str) -> str:
    normalized = status.lower()
    return {
        "completed": "done",
        "failed": "fail",
        "in_progress": "run",
        "retry_pending": "wait",
        "clean": "ok",
        "attention": "warn",
        "issues": "err",
        "available": "ok",
    }.get(normalized, normalized[:5] or "n/a")


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
