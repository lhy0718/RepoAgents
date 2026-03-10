from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from repoagents.config import LoadedConfig
from repoagents.models import RunRecord
from repoagents.models.domain import utc_now
from repoagents.orchestrator import RunStateStore
from repoagents._related_report_details.rendering import (
    build_related_report_detail_block,
    build_related_report_detail_html_layout,
    build_related_report_detail_line_layout,
    build_related_report_detail_summary,
    collect_related_report_warning_lines,
    format_related_report_detail_title,
    render_related_report_detail_html_fragments,
    render_related_report_detail_lines,
)
from repoagents.report_policy import build_report_policy_drift_guidance
from repoagents.sync_artifacts import (
    SyncAppliedRetentionGroup,
    SyncAppliedRetentionIssueSummary,
    summarize_sync_applied_retention,
)
from repoagents.utils.files import write_text_file


@dataclass(frozen=True, slots=True)
class DashboardBuildResult:
    output_path: Path
    total_runs: int
    visible_runs: int
    exported_paths: dict[str, Path]


VALID_DASHBOARD_FORMATS = ("html", "json", "markdown")
REPORT_EXPORTS = (
    ("sync-audit", "Sync audit", "sync-audit.json", "sync-audit.md"),
    ("sync-health", "Sync health", "sync-health.json", "sync-health.md"),
    ("github-smoke", "GitHub smoke", "github-smoke.json", "github-smoke.md"),
    ("cleanup-preview", "Cleanup preview", "cleanup-preview.json", "cleanup-preview.md"),
    ("cleanup-result", "Cleanup result", "cleanup-result.json", "cleanup-result.md"),
    ("ops-status", "Ops status", "ops-status.json", "ops-status.md"),
    ("ops-brief", "Ops brief", "ops-brief.json", "ops-brief.md"),
)
OPS_SNAPSHOT_ENTRY_PREVIEW_LIMIT = 5
SEVERITY_ORDER = {
    "clean": 0,
    "attention": 1,
    "issues": 2,
}
INTEGRITY_FINDING_HINTS = {
    "missing_manifest": "run `repoagents sync repair --dry-run` to rebuild manifest state from archived files",
    "invalid_manifest_json": "inspect `manifest.json`, then run `repoagents sync repair --dry-run` to reconstruct it",
    "invalid_manifest_format": "rewrite `manifest.json` as a JSON array or let `repoagents sync repair --dry-run` rebuild it",
    "invalid_entry_type": "run `repoagents sync repair --dry-run` to drop malformed manifest entries",
    "duplicate_entry_key": "run `repoagents sync repair --dry-run` to canonicalize duplicate manifest entries",
    "dangling_archive_reference": "review deleted or moved archive files under `.ai-repoagents/sync-applied/` before repair",
    "duplicate_archive_reference": "run `repoagents sync repair --dry-run` to deduplicate archive references",
    "mismatched_archived_path": "run `repoagents sync repair --dry-run` to realign archived path metadata",
    "missing_archived_relative_path": "run `repoagents sync repair --dry-run` to restore archived_relative_path metadata",
    "orphan_archive_file": "review orphan archives and adopt them with `repoagents sync repair --dry-run`",
    "missing_handoff_metadata": "run `repoagents sync repair --dry-run` to rebuild handoff metadata",
    "handoff_group_mismatch": "run `repoagents sync repair --dry-run` to recalculate handoff linkage",
}


def build_dashboard(
    loaded: LoadedConfig,
    *,
    output_path: Path | None = None,
    limit: int = 50,
    refresh_seconds: int = 0,
    formats: tuple[str, ...] = ("html",),
) -> DashboardBuildResult:
    store = RunStateStore(loaded.state_dir / "runs.json")
    all_records = store.all()
    visible_records = all_records[:limit]
    normalized_formats = normalize_dashboard_formats(formats)
    target = output_path or (loaded.ai_root / "dashboard" / "index.html")
    export_paths = resolve_dashboard_export_paths(target, normalized_formats)
    snapshot = build_dashboard_snapshot(
        loaded=loaded,
        all_records=all_records,
        visible_records=visible_records,
        output_path=export_paths.get("html", target),
        refresh_seconds=refresh_seconds,
        sync_limit=limit,
    )
    if "html" in export_paths:
        write_text_file(export_paths["html"], render_dashboard_html(snapshot=snapshot))
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_dashboard_json(snapshot))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_dashboard_markdown(snapshot))
    primary_path = export_paths.get("html")
    if primary_path is None:
        primary_path = export_paths[normalized_formats[0]]
    return DashboardBuildResult(
        output_path=primary_path,
        total_runs=len(all_records),
        visible_runs=len(visible_records),
        exported_paths=export_paths,
    )


def normalize_dashboard_formats(formats: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if not formats:
        return ("html",)
    normalized: list[str] = []
    for value in formats:
        lowered = value.strip().lower()
        if not lowered:
            continue
        if lowered == "all":
            for item in VALID_DASHBOARD_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_DASHBOARD_FORMATS:
            valid = ", ".join((*VALID_DASHBOARD_FORMATS, "all"))
            raise ValueError(f"Unsupported dashboard format '{value}'. Expected one of: {valid}")
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("html",))


def resolve_dashboard_export_paths(base_output: Path, formats: tuple[str, ...]) -> dict[str, Path]:
    target = base_output
    if target.suffix.lower() not in {".html", ".json", ".md"}:
        target = target / "index.html"
    suffix_map = {
        "html": ".html",
        "json": ".json",
        "markdown": ".md",
    }
    return {
        export_format: target.with_suffix(suffix_map[export_format]) for export_format in formats
    }


def build_dashboard_snapshot(
    *,
    loaded: LoadedConfig,
    all_records: list[RunRecord],
    visible_records: list[RunRecord],
    output_path: Path,
    refresh_seconds: int = 0,
    sync_limit: int = 50,
) -> dict[str, object]:
    counts = Counter(record.status.value for record in all_records)
    rendered_at = utc_now().isoformat()
    last_updated = all_records[0].updated_at.isoformat() if all_records else "n/a"
    log_file = loaded.logs_dir / "repoagents.jsonl"
    snapshot_runs = [
        _serialize_run_record(loaded, record, output_path) for record in visible_records
    ]
    sync_handoffs = _load_sync_handoffs(
        loaded=loaded,
        output_path=output_path,
        limit=sync_limit,
    )
    sync_retention = _serialize_sync_retention_snapshot(
        loaded=loaded,
        output_path=output_path,
        limit=sync_limit,
    )
    ops_snapshots = _load_ops_snapshot_summaries(
        loaded=loaded,
        output_path=output_path,
        rendered_at=rendered_at,
    )
    reports = _load_report_summaries(
        loaded=loaded,
        output_path=output_path,
        rendered_at=rendered_at,
    )
    hero = _build_hero_snapshot(reports, include_policy_drift=True)
    policy = _build_report_freshness_policy_snapshot(loaded)
    return {
        "meta": {
            "rendered_at": rendered_at,
            "repo_name": loaded.repo_root.name,
            "repo_root": str(loaded.repo_root),
            "output_path": str(output_path),
            "last_updated": last_updated,
            "refresh_seconds": refresh_seconds,
        },
        "runtime": {
            "config_path": str(loaded.config_path),
            "state_path": str(loaded.state_dir / "runs.json"),
            "artifacts_dir": str(loaded.artifacts_dir),
            "workspace_root": str(loaded.workspace_root),
            "reports_dir": str(loaded.reports_dir),
            "logs_path": str(log_file) if log_file.exists() else None,
        },
        "counts": {
            "total_runs": len(all_records),
            "visible_runs": len(visible_records),
            "total_sync_handoffs": sync_handoffs["total"],
            "visible_sync_handoffs": len(sync_handoffs["entries"]),
            "total_sync_retention_issues": sync_retention["total_issues"],
            "visible_sync_retention_issues": len(sync_retention["entries"]),
            "prunable_sync_groups": sync_retention["prunable_groups"],
            "prunable_sync_bytes": sync_retention["prunable_bytes"],
            "repair_needed_sync_issues": sync_retention["repair_needed_issues"],
            "ops_snapshot_entries": ops_snapshots["history_entry_count"],
            "ops_snapshot_archives": ops_snapshots["archive_entry_count"],
            "ops_snapshot_dropped_entries": ops_snapshots["dropped_entry_count"],
            "available_reports": reports["total"],
            "aging_reports": reports["aging_total"],
            "future_reports": reports["future_total"],
            "unknown_reports": reports["unknown_total"],
            "stale_reports": reports["stale_total"],
            "cleanup_reports": reports["cleanup_total"],
            "cleanup_aging_reports": reports["cleanup_aging_total"],
            "cleanup_future_reports": reports["cleanup_future_total"],
            "cleanup_unknown_reports": reports["cleanup_unknown_total"],
            "stale_cleanup_reports": reports["cleanup_freshness"].get("stale", 0),
            "policy_drift_reports": reports["policy_drift_total"],
            "policy_embedded_reports": reports["policy_embedded_total"],
            "policy_metadata_missing_reports": reports["policy_missing_total"],
            "by_status": dict(sorted(counts.items())),
        },
        "hero": hero,
        "policy": policy,
        "runs": snapshot_runs,
        "sync_handoffs": sync_handoffs["entries"],
        "sync_retention": sync_retention,
        "ops_snapshots": ops_snapshots,
        "reports": reports,
    }


def build_report_health_snapshot(*, loaded: LoadedConfig) -> dict[str, object]:
    reports = _load_report_summaries(
        loaded=loaded,
        output_path=loaded.ai_root / "dashboard" / "index.html",
        rendered_at=utc_now().isoformat(),
    )
    hero = _build_hero_snapshot(reports)
    policy = _build_report_freshness_policy_snapshot(loaded)
    return {
        "hero": hero,
        "policy": policy,
        "reports": reports,
    }


def build_ops_snapshot_status_snapshot(*, loaded: LoadedConfig) -> dict[str, object]:
    return _load_ops_snapshot_summaries(
        loaded=loaded,
        output_path=loaded.ai_root / "dashboard" / "index.html",
        rendered_at=utc_now().isoformat(),
    )


def render_dashboard_html(*, snapshot: dict[str, object]) -> str:
    meta = _snapshot_section(snapshot, "meta")
    runtime = _snapshot_section(snapshot, "runtime")
    counts = _snapshot_section(snapshot, "counts")
    runs = _snapshot_runs(snapshot)
    sync_handoffs = _snapshot_sync_handoffs(snapshot)
    sync_retention = _snapshot_sync_retention(snapshot)
    ops_snapshots = _snapshot_ops_snapshots(snapshot)
    reports = _snapshot_reports(snapshot)
    hero = _snapshot_section(snapshot, "hero")
    policy = _snapshot_section(snapshot, "policy")
    rendered_at = str(meta["rendered_at"])
    last_updated = str(meta["last_updated"])
    output_path = Path(str(meta["output_path"]))
    refresh_seconds = int(meta["refresh_seconds"])
    repo_name = str(meta["repo_name"])
    total_runs = int(counts["total_runs"])
    visible_runs = int(counts["visible_runs"])
    status_counts = Counter({key: int(value) for key, value in _snapshot_mapping(counts, "by_status").items()})
    runtime_links = [
        _render_link_chip("config", _relative_href(output_path, Path(str(runtime["config_path"])))),
        _render_link_chip("runs.json", _relative_href(output_path, Path(str(runtime["state_path"])))),
        _render_link_chip("artifacts", _relative_href(output_path, Path(str(runtime["artifacts_dir"])))),
        _render_link_chip("workspaces", _relative_href(output_path, Path(str(runtime["workspace_root"])))),
        _render_link_chip("reports", _relative_href(output_path, Path(str(runtime["reports_dir"])))),
    ]
    logs_path = runtime.get("logs_path")
    if isinstance(logs_path, str) and logs_path:
        runtime_links.append(
            _render_link_chip(
                "logs",
                _relative_href(output_path, Path(logs_path)),
            )
        )
    latest_ops_href = _string_or_none(ops_snapshots.get("latest_json_href"))
    history_ops_href = _string_or_none(ops_snapshots.get("history_json_href"))
    if latest_ops_href:
        runtime_links.append(_render_link_chip("ops latest", latest_ops_href))
    if history_ops_href:
        runtime_links.append(_render_link_chip("ops history", history_ops_href))

    summary_cards = [
        _render_metric_card("Visible runs", str(visible_runs)),
        _render_metric_card("Total runs", str(total_runs)),
        _render_metric_card("Sync handoffs", str(counts["visible_sync_handoffs"])),
        _render_metric_card("Completed", str(status_counts.get("completed", 0))),
        _render_metric_card("Failed", str(status_counts.get("failed", 0))),
        _render_metric_card("Retry pending", str(status_counts.get("retry_pending", 0))),
    ]
    if status_counts.get("in_progress", 0):
        summary_cards.append(_render_metric_card("In progress", str(status_counts["in_progress"])))
    hero_reporting_chips = "".join(
        _render_hero_chip(chip)
        for chip in _list_of_dicts(hero["reporting_chips"])
    )
    hero_alert_severity = _string_or_none(hero.get("severity")) or "clean"
    hero_alert_title = _string_or_none(hero.get("title")) or "Dashboard summary"
    hero_alert_summary = _string_or_none(hero.get("summary")) or ""

    runs_markup = "\n".join(_render_run_card(run) for run in runs)
    if not runs_markup:
        runs_markup = """
        <article class="empty-state">
          <h2>No runs recorded yet</h2>
          <p>Run <code>repoagents run --once</code>, <code>repoagents trigger &lt;issue-id&gt;</code>, or a webhook-triggered execution to populate the dashboard.</p>
        </article>
        """
    handoff_markup = "\n".join(_render_sync_handoff_card(handoff) for handoff in sync_handoffs)
    if not handoff_markup:
        handoff_markup = """
        <article class="empty-state">
          <h2>No sync handoffs archived yet</h2>
          <p>Apply staged tracker handoffs with <code>repoagents sync apply</code> to populate this section.</p>
        </article>
        """
    retention_summary_cards = [
        _render_metric_card("Applied sync issues", str(sync_retention["total_issues"])),
        _render_metric_card("Prunable groups", str(sync_retention["prunable_groups"])),
        _render_metric_card("Prunable bytes", str(sync_retention["prunable_bytes_human"])),
        _render_metric_card("Repair needed", str(sync_retention["repair_needed_issues"])),
    ]
    retention_markup = "\n".join(
        _render_sync_retention_issue_card(entry)
        for entry in _list_of_dicts(sync_retention["entries"])
    )
    if not retention_markup:
        retention_markup = """
        <article class="empty-state">
          <h2>No applied sync archives yet</h2>
          <p>Apply staged tracker handoffs with <code>repoagents sync apply</code> to populate retention analysis.</p>
        </article>
        """
    ops_summary_cards = [
        _render_metric_card("Indexed ops snapshots", str(ops_snapshots["history_entry_count"])),
        _render_metric_card("Ops archives", str(ops_snapshots["archive_entry_count"])),
        _render_metric_card("Ops history limit", str(ops_snapshots["history_limit"])),
    ]
    if int(ops_snapshots["dropped_entry_count"]) > 0:
        ops_summary_cards.append(
            _render_metric_card(
                "Dropped ops entries",
                str(ops_snapshots["dropped_entry_count"]),
                tone="attention",
                note="Older managed bundles may be eligible for prune.",
            )
        )
    ops_markup = _render_ops_snapshot_section(ops_snapshots)
    report_link_chips = [
        _render_link_chip(str(entry["label"]), _string_or_none(entry["json_href"]) or _string_or_none(entry["markdown_href"]))
        for entry in _list_of_dicts(reports["entries"])
    ]
    runtime_links.extend(report_link_chips)
    report_summary_cards = [
        _render_metric_card("Reports", str(reports["total"])),
        _render_metric_card(
            "Report freshness",
            _format_report_freshness_summary(_snapshot_mapping(reports, "freshness")),
            tone=_string_or_none(reports.get("report_summary_severity")),
            note=_string_or_none(reports.get("report_summary_severity_reason")),
        ),
        _render_metric_card("Aging reports", str(reports["aging_total"])),
        _render_metric_card("Future reports", str(reports["future_total"])),
    ]
    if int(reports["unknown_total"]) > 0:
        report_summary_cards.append(
            _render_metric_card("Unknown freshness reports", str(reports["unknown_total"]))
        )
    if int(reports.get("policy_drift_total", 0)) > 0:
        report_summary_cards.append(
            _render_metric_card(
                "Policy drift reports",
                str(reports["policy_drift_total"]),
                tone="attention",
                note=_report_policy_drift_guidance_summary(),
            )
        )
    if int(reports["cleanup_total"]) > 0:
        report_summary_cards.append(
            _render_metric_card(
                "Cleanup freshness",
                _format_report_freshness_summary(_snapshot_mapping(reports, "cleanup_freshness")),
                tone=_string_or_none(reports.get("cleanup_freshness_severity")),
                note=_string_or_none(reports.get("cleanup_freshness_severity_reason")),
            )
        )
        report_summary_cards.append(
            _render_metric_card("Cleanup aging reports", str(reports["cleanup_aging_total"]))
        )
        report_summary_cards.append(
            _render_metric_card("Cleanup future reports", str(reports["cleanup_future_total"]))
        )
        if int(reports["cleanup_unknown_total"]) > 0:
            report_summary_cards.append(
                _render_metric_card(
                    "Cleanup unknown freshness reports",
                    str(reports["cleanup_unknown_total"]),
                )
            )
        report_summary_cards.append(
            _render_metric_card("Stale cleanup reports", str(reports["cleanup_stale_total"]))
        )
    report_markup = "\n".join(
        _render_report_card(entry)
        for entry in _list_of_dicts(reports["entries"])
    )
    if not report_markup:
        report_markup = """
        <article class="empty-state">
          <h2>No report exports yet</h2>
          <p>Generate <code>repoagents sync audit --format all</code> or <code>repoagents clean --report</code> to add report links here.</p>
        </article>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>RepoAgents Operations Dashboard</title>
    <style>
      :root {{
        --paper: #f6f1e6;
        --paper-2: #fffaf1;
        --ink: #13283f;
        --muted: #526579;
        --accent: #d35f3f;
        --accent-2: #1f6b74;
        --ok: #2f6b4f;
        --warn: #996515;
        --danger: #922f3a;
        --card: rgba(255, 251, 243, 0.88);
        --border: rgba(19, 40, 63, 0.14);
        --shadow: 0 24px 60px rgba(19, 40, 63, 0.14);
      }}
      * {{
        box-sizing: border-box;
      }}
      body {{
        margin: 0;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(211, 95, 63, 0.18), transparent 28rem),
          radial-gradient(circle at top right, rgba(31, 107, 116, 0.20), transparent 30rem),
          linear-gradient(180deg, #f9f4ea 0%, #efe5d4 100%);
        font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Palatino, serif;
      }}
      a {{
        color: inherit;
      }}
      .shell {{
        width: min(1180px, calc(100vw - 2rem));
        margin: 0 auto;
        padding: 2rem 0 4rem;
      }}
      .hero {{
        position: relative;
        overflow: hidden;
        margin: 1rem 0 1.5rem;
        padding: 2rem;
        border: 1px solid rgba(255, 255, 255, 0.45);
        border-radius: 28px;
        background:
          linear-gradient(135deg, rgba(255, 250, 241, 0.9), rgba(250, 235, 215, 0.86)),
          rgba(255, 255, 255, 0.8);
        box-shadow: var(--shadow);
      }}
      .hero-issues {{
        border-color: rgba(146, 47, 58, 0.26);
      }}
      .hero-attention {{
        border-color: rgba(153, 101, 21, 0.24);
      }}
      .hero-clean {{
        border-color: rgba(47, 107, 79, 0.22);
      }}
      .eyebrow {{
        margin: 0 0 0.35rem;
        color: var(--accent-2);
        font: 600 0.8rem/1.2 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
      h1 {{
        margin: 0;
        font-size: clamp(2rem, 5vw, 3.75rem);
        line-height: 0.95;
      }}
      .subtitle {{
        max-width: 52rem;
        margin: 0.9rem 0 0;
        color: var(--muted);
        font-size: 1.05rem;
        line-height: 1.55;
      }}
      .meta-row, .link-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin-top: 1rem;
      }}
      .hero-alert {{
        margin-top: 1rem;
        padding: 1rem 1.1rem;
        border-radius: 22px;
        border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.55);
      }}
      .hero-alert-issues {{
        border-color: rgba(146, 47, 58, 0.22);
        background: rgba(255, 244, 244, 0.82);
      }}
      .hero-alert-attention {{
        border-color: rgba(153, 101, 21, 0.22);
        background: rgba(255, 249, 239, 0.82);
      }}
      .hero-alert-clean {{
        border-color: rgba(47, 107, 79, 0.20);
        background: rgba(244, 251, 246, 0.82);
      }}
      .hero-alert-title {{
        margin: 0;
        font-size: 1rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        font-family: "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
      }}
      .hero-alert-copy {{
        margin: 0.5rem 0 0;
        color: var(--ink);
        line-height: 1.55;
      }}
      .hero-chip-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.65rem;
        margin-top: 0.85rem;
      }}
      .hero-chip {{
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.58rem 0.82rem;
        border-radius: 999px;
        border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.72);
        font: 500 0.76rem/1.25 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
      }}
      .meta-chip, .link-chip {{
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.6rem 0.9rem;
        border-radius: 999px;
        border: 1px solid var(--border);
        background: rgba(255, 255, 255, 0.64);
        font: 500 0.86rem/1.2 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
        text-decoration: none;
      }}
      .section-title {{
        margin: 2rem 0 0.8rem;
        font-size: 1.2rem;
      }}
      .metrics {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 0.9rem;
      }}
      .toolbar {{
        display: grid;
        grid-template-columns: minmax(220px, 2fr) repeat(2, minmax(160px, 1fr));
        gap: 0.9rem;
        margin-top: 1rem;
      }}
      .control {{
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
      }}
      .control label {{
        color: var(--muted);
        font: 600 0.74rem/1.2 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      .control input,
      .control select {{
        width: 100%;
        padding: 0.85rem 0.95rem;
        border-radius: 16px;
        border: 1px solid rgba(19, 40, 63, 0.18);
        background: rgba(255, 255, 255, 0.84);
        color: var(--ink);
        font: 500 0.95rem/1.3 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
      }}
      .helper-row {{
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        gap: 0.75rem;
        margin-top: 0.8rem;
        color: var(--muted);
        font: 500 0.8rem/1.3 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
      }}
      .metric-card {{
        padding: 1rem;
        border-radius: 22px;
        border: 1px solid var(--border);
        background: var(--card);
        box-shadow: 0 14px 35px rgba(19, 40, 63, 0.08);
      }}
      .metric-card-issues {{
        border-color: rgba(146, 47, 58, 0.25);
        background: rgba(255, 244, 244, 0.9);
      }}
      .metric-card-attention {{
        border-color: rgba(153, 101, 21, 0.24);
        background: rgba(255, 249, 239, 0.9);
      }}
      .metric-card-clean {{
        border-color: rgba(47, 107, 79, 0.24);
        background: rgba(244, 251, 246, 0.9);
      }}
      .metric-label {{
        display: block;
        color: var(--muted);
        font: 600 0.74rem/1.2 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      .metric-value {{
        display: block;
        margin-top: 0.45rem;
        font-size: 1.95rem;
      }}
      .metric-note {{
        display: block;
        margin-top: 0.4rem;
        color: var(--muted);
        font: 500 0.74rem/1.35 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
      }}
      .runs,
      .handoffs,
      .retention,
      .reports {{
        display: grid;
        gap: 1rem;
      }}
      .run-card,
      .handoff-card,
      .retention-card,
      .report-card {{
        padding: 1.25rem;
        border-radius: 24px;
        border: 1px solid var(--border);
        background: rgba(255, 251, 243, 0.88);
        box-shadow: 0 18px 45px rgba(19, 40, 63, 0.08);
      }}
      .run-card[hidden] {{
        display: none;
      }}
      .run-head {{
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        gap: 0.9rem;
        align-items: flex-start;
      }}
      .run-title {{
        margin: 0.2rem 0 0;
        font-size: 1.45rem;
      }}
      .run-subtitle {{
        margin: 0;
        color: var(--muted);
        font: 500 0.82rem/1.25 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
      }}
      .status {{
        display: inline-flex;
        align-items: center;
        padding: 0.5rem 0.8rem;
        border-radius: 999px;
        font: 700 0.76rem/1 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      .status-completed {{ background: rgba(47, 107, 79, 0.15); color: var(--ok); }}
      .status-failed {{ background: rgba(146, 47, 58, 0.15); color: var(--danger); }}
      .status-retry-pending {{ background: rgba(153, 101, 21, 0.16); color: var(--warn); }}
      .status-in-progress {{ background: rgba(31, 107, 116, 0.15); color: var(--accent-2); }}
      .status-sync {{ background: rgba(31, 107, 116, 0.15); color: var(--accent-2); }}
      .status-prunable {{ background: rgba(153, 101, 21, 0.16); color: var(--warn); }}
      .status-stable {{ background: rgba(47, 107, 79, 0.15); color: var(--ok); }}
      .status-repair-needed {{ background: rgba(146, 47, 58, 0.15); color: var(--danger); }}
      .status-ok, .status-cleaned {{ background: rgba(47, 107, 79, 0.15); color: var(--ok); }}
      .status-attention, .status-preview {{ background: rgba(153, 101, 21, 0.16); color: var(--warn); }}
      .status-issues, .status-invalid {{ background: rgba(146, 47, 58, 0.15); color: var(--danger); }}
      .status-available, .status-clean {{ background: rgba(31, 107, 116, 0.15); color: var(--accent-2); }}
      .status-skipped, .status-pending {{ background: rgba(19, 40, 63, 0.08); color: var(--ink); }}
      .run-grid {{
        display: grid;
        grid-template-columns: 2.2fr 1fr;
        gap: 1rem;
        margin-top: 1rem;
      }}
      .panel {{
        min-width: 0;
        padding: 0.95rem 1rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.52);
        border: 1px solid rgba(19, 40, 63, 0.1);
      }}
      .panel h3 {{
        margin: 0 0 0.55rem;
        font-size: 0.95rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        font-family: "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
      }}
      .copy {{
        margin: 0;
        color: var(--ink);
        line-height: 1.55;
        white-space: pre-wrap;
      }}
      .error {{
        color: var(--danger);
      }}
      .token-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
      }}
      .token {{
        display: inline-flex;
        padding: 0.42rem 0.72rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid var(--border);
        font: 500 0.76rem/1.2 "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
        text-decoration: none;
      }}
      .list {{
        margin: 0;
        padding-left: 1rem;
        color: var(--ink);
      }}
      .list li + li {{
        margin-top: 0.4rem;
      }}
      .empty-state {{
        padding: 2rem;
        border-radius: 24px;
        border: 1px dashed rgba(19, 40, 63, 0.24);
        background: rgba(255, 255, 255, 0.45);
      }}
      .group-list {{
        margin: 0;
        padding-left: 1rem;
      }}
      .group-list li + li {{
        margin-top: 0.45rem;
      }}
      code {{
        font-family: "IBM Plex Mono", "SFMono-Regular", Menlo, monospace;
      }}
      @media (max-width: 860px) {{
        .toolbar {{
          grid-template-columns: 1fr;
        }}
        .run-grid {{
          grid-template-columns: 1fr;
        }}
        .hero {{
          padding: 1.35rem;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="hero hero-{escape(hero_alert_severity)}" data-default-refresh-seconds="{refresh_seconds}">
        <p class="eyebrow">RepoAgents operations dashboard</p>
        <h1>Repository runs at a glance</h1>
        <p class="subtitle">This view is generated from local RepoAgents state. It highlights the latest runs, persisted artifacts, retry posture, and failure reasons without needing a separate service.</p>
        <section class="hero-alert hero-alert-{escape(hero_alert_severity)}">
          <h2 class="hero-alert-title">{escape(hero_alert_title)}</h2>
          <p class="hero-alert-copy">{escape(hero_alert_summary)}</p>
          <div class="hero-chip-row">
            {hero_reporting_chips}
          </div>
        </section>
        <div class="meta-row">
          <span class="meta-chip">rendered_at {escape(rendered_at)}</span>
          <span class="meta-chip">repo {escape(repo_name)}</span>
          <span class="meta-chip">last_updated {escape(last_updated)}</span>
          <span class="meta-chip">freshness_policy {escape(str(policy['summary']))}</span>
        </div>
        <div class="link-row">
          {"".join(runtime_links)}
        </div>
      </section>

      <section>
        <h2 class="section-title">Run summary</h2>
        <div class="metrics">
          {"".join(summary_cards)}
        </div>
        <div class="toolbar">
          <div class="control">
            <label for="run-search">Search runs</label>
            <input id="run-search" type="search" placeholder="issue title, run id, summary, error" />
          </div>
          <div class="control">
            <label for="status-filter">Status</label>
            <select id="status-filter">
              <option value="all">All statuses</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
              <option value="retry_pending">retry_pending</option>
              <option value="in_progress">in_progress</option>
              <option value="pending">pending</option>
              <option value="skipped">skipped</option>
            </select>
          </div>
          <div class="control">
            <label for="refresh-interval">Auto refresh</label>
            <select id="refresh-interval">
              <option value="0">Off</option>
              <option value="10">10s</option>
              <option value="30">30s</option>
              <option value="60">60s</option>
              <option value="120">120s</option>
            </select>
          </div>
        </div>
        <div class="helper-row">
          <span id="filter-summary">Showing {visible_runs} loaded runs.</span>
          <span id="refresh-status">Auto refresh is off.</span>
        </div>
      </section>

      <section>
        <h2 class="section-title">Latest runs</h2>
        <div class="runs">
          {runs_markup}
        </div>
        <article id="filter-empty" class="empty-state" hidden>
          <h2>No runs match the current filter</h2>
          <p>Clear the search box or switch the status filter back to <code>All statuses</code>.</p>
        </article>
      </section>

      <section>
        <h2 class="section-title">Sync handoffs</h2>
        <div class="handoffs">
          {handoff_markup}
        </div>
      </section>

      <section>
        <h2 class="section-title">Sync retention</h2>
        <div class="metrics">
          {"".join(retention_summary_cards)}
        </div>
        <div class="retention" style="margin-top: 1rem;">
          {retention_markup}
        </div>
      </section>

      <section>
        <h2 class="section-title">Ops snapshots</h2>
        <div class="metrics">
          {"".join(ops_summary_cards)}
        </div>
        <div class="reports" style="margin-top: 1rem;">
          {ops_markup}
        </div>
      </section>

      <section>
        <h2 class="section-title">Reports</h2>
        <div class="metrics">
          {"".join(report_summary_cards)}
        </div>
        <div class="reports" style="margin-top: 1rem;">
          {report_markup}
        </div>
      </section>
    </main>
    <script>
      (() => {{
        const searchInput = document.getElementById("run-search");
        const statusFilter = document.getElementById("status-filter");
        const refreshControl = document.getElementById("refresh-interval");
        const filterSummary = document.getElementById("filter-summary");
        const refreshStatus = document.getElementById("refresh-status");
        const emptyState = document.getElementById("filter-empty");
        const visibleRunsMetric = document.getElementById("visible-runs-count");
        const cards = Array.from(document.querySelectorAll(".run-card"));
        const defaultRefreshSeconds = Number(
          document.querySelector(".hero")?.dataset.defaultRefreshSeconds || "0"
        );
        let refreshTimer = null;

        const applyFilters = () => {{
          const query = (searchInput.value || "").trim().toLowerCase();
          const selectedStatus = statusFilter.value;
          let visibleCount = 0;
          cards.forEach((card) => {{
            const searchText = card.dataset.search || "";
            const status = card.dataset.status || "";
            const matchesQuery = !query || searchText.includes(query);
            const matchesStatus = selectedStatus === "all" || status === selectedStatus;
            const visible = matchesQuery && matchesStatus;
            card.hidden = !visible;
            if (visible) {{
              visibleCount += 1;
            }}
          }});
          if (visibleRunsMetric) {{
            visibleRunsMetric.textContent = String(visibleCount);
          }}
          filterSummary.textContent = `Showing ${{visibleCount}} of ${{cards.length}} loaded runs.`;
          emptyState.hidden = visibleCount !== 0;
        }};

        const updateRefresh = () => {{
          const seconds = Number(refreshControl.value || "0");
          if (refreshTimer !== null) {{
            window.clearInterval(refreshTimer);
            refreshTimer = null;
          }}
          if (seconds > 0) {{
            refreshStatus.textContent = `Auto refresh every ${{seconds}}s.`;
            refreshTimer = window.setInterval(() => window.location.reload(), seconds * 1000);
          }} else {{
            refreshStatus.textContent = "Auto refresh is off.";
          }}
        }};

        if (searchInput) {{
          searchInput.addEventListener("input", applyFilters);
        }}
        if (statusFilter) {{
          statusFilter.addEventListener("change", applyFilters);
        }}
        if (refreshControl) {{
          if (
            defaultRefreshSeconds > 0 &&
            !Array.from(refreshControl.options).some((option) => option.value === String(defaultRefreshSeconds))
          ) {{
            const option = document.createElement("option");
            option.value = String(defaultRefreshSeconds);
            option.textContent = `${{defaultRefreshSeconds}}s`;
            refreshControl.append(option);
          }}
          refreshControl.value = String(defaultRefreshSeconds);
          refreshControl.addEventListener("change", updateRefresh);
        }}

        applyFilters();
        updateRefresh();
      }})();
    </script>
  </body>
</html>
"""


def render_dashboard_json(snapshot: dict[str, object]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


def render_dashboard_markdown(snapshot: dict[str, object]) -> str:
    meta = _snapshot_section(snapshot, "meta")
    counts = _snapshot_section(snapshot, "counts")
    hero = _snapshot_section(snapshot, "hero")
    policy = _snapshot_section(snapshot, "policy")
    runs = _snapshot_runs(snapshot)
    sync_handoffs = _snapshot_sync_handoffs(snapshot)
    sync_retention = _snapshot_sync_retention(snapshot)
    ops_snapshots = _snapshot_ops_snapshots(snapshot)
    reports = _snapshot_reports(snapshot)
    status_counts = _snapshot_mapping(counts, "by_status")
    lines = [
        "# RepoAgents Dashboard Snapshot",
        "",
        f"- rendered_at: {meta['rendered_at']}",
        f"- repo: {meta['repo_name']}",
        f"- total_runs: {counts['total_runs']}",
        f"- visible_runs: {counts['visible_runs']}",
        f"- total_sync_handoffs: {counts['total_sync_handoffs']}",
        f"- visible_sync_handoffs: {counts['visible_sync_handoffs']}",
        f"- ops_snapshot_entries: {counts['ops_snapshot_entries']}",
        f"- ops_snapshot_archives: {counts['ops_snapshot_archives']}",
        f"- ops_snapshot_dropped_entries: {counts['ops_snapshot_dropped_entries']}",
        "",
        "## Policy",
        f"- report_freshness_policy: {policy['summary']}",
        f"- unknown_issues_threshold: {policy['report_freshness_policy']['unknown_issues_threshold']}",
        f"- stale_issues_threshold: {policy['report_freshness_policy']['stale_issues_threshold']}",
        f"- future_attention_threshold: {policy['report_freshness_policy']['future_attention_threshold']}",
        f"- aging_attention_threshold: {policy['report_freshness_policy']['aging_attention_threshold']}",
        "",
        "## Hero",
        f"- severity: {hero['severity']}",
        f"- title: {hero['title']}",
        f"- summary: {hero['summary']}",
        "",
        "## Status counts",
    ]
    hero_chips = _list_of_dicts(hero["reporting_chips"])
    if hero_chips:
        lines.append("- reporting_chips:")
        for chip in hero_chips:
            lines.append(
                f"  - {chip['label']}: severity={chip['severity']} value={chip['value']}"
            )
        lines.append("")
    if status_counts:
        for status, value in sorted(status_counts.items()):
            lines.append(f"- {status}: {value}")
    else:
        lines.append("- none")
    lines.extend(["", "## Latest runs"])
    if not runs:
        lines.append("- No runs recorded yet.")
    else:
        for run in runs:
            lines.extend(
                [
                    "",
                    f"### Issue #{run['issue_id']}: {run['issue_title']}",
                    f"- run_id: {run['run_id']}",
                    f"- status: {run['status']}",
                    f"- backend: {run['backend_mode']}",
                    f"- updated_at: {run['updated_at']}",
                    f"- attempts: {run['attempts']}",
                    f"- summary: {run['summary'] or 'No summary recorded.'}",
                ]
            )
            if run["current_role"]:
                lines.append(f"- current_role: {run['current_role']}")
            if run["next_retry_at"]:
                lines.append(f"- next_retry_at: {run['next_retry_at']}")
            if run["last_error"]:
                lines.append(f"- last_error: {run['last_error']}")
            artifact_labels = [artifact["label"] for artifact in run["artifacts"]]
            lines.append(f"- artifacts: {', '.join(artifact_labels) if artifact_labels else 'none'}")
            workspace_path = run["workspace_path"] or "none"
            lines.append(f"- workspace: {workspace_path}")
            external_actions = run["external_actions"]
            if external_actions:
                lines.append("- external_actions:")
                for action in external_actions:
                    lines.append(
                        f"  - {action['action']} executed={action['executed']} reason={action['reason']}"
                    )
    lines.extend(["", "## Sync handoffs"])
    if not sync_handoffs:
        lines.append("- No sync handoffs archived yet.")
    else:
        for handoff in sync_handoffs:
            issue_label = handoff["issue_id"] if handoff["issue_id"] is not None else "unknown"
            lines.extend(
                [
                    "",
                    f"### {handoff['artifact_role'] or handoff['action']} · issue #{issue_label}",
                    f"- tracker: {handoff['tracker']}",
                    f"- action: {handoff['action']}",
                    f"- applied_at: {handoff['applied_at']}",
                    f"- staged_at: {handoff['staged_at'] or 'n/a'}",
                    f"- summary: {handoff['summary'] or 'No summary recorded.'}",
                    f"- issue_key: {handoff['issue_key'] or 'n/a'}",
                    f"- bundle_key: {handoff['bundle_key'] or 'n/a'}",
                    f"- manifest: {handoff['manifest_path']}",
                    f"- archived: {handoff['archived_path'] or 'n/a'}",
                ]
            )
            source_relative_path = handoff["source_relative_path"] or "n/a"
            lines.append(f"- source_relative_path: {source_relative_path}")
            ref_pairs = [
                f"{key}={value}"
                for key, value in _snapshot_mapping(handoff, "refs").items()
                if value not in (None, "")
            ]
            lines.append(f"- refs: {', '.join(ref_pairs) if ref_pairs else 'none'}")
            normalized_links = _list_of_dicts(handoff["normalized_links"])
            if normalized_links:
                lines.append("- normalized_links:")
                for link in normalized_links:
                    lines.append(
                        f"  - {link['label']}: {link['target']}"
                    )
            handoff_info = _snapshot_mapping(handoff, "handoff")
            lines.append(
                f"- handoff_group: key={handoff_info.get('group_key') or 'n/a'} size={handoff_info.get('group_size') or 0} index={handoff_info.get('group_index') or 0}"
            )
    lines.extend(
        [
            "",
            "## Sync retention",
            f"- keep_groups_per_issue: {sync_retention['keep_groups_per_issue']}",
            f"- total_issues: {sync_retention['total_issues']}",
            f"- eligible_issues: {sync_retention['eligible_issues']}",
            f"- repair_needed_issues: {sync_retention['repair_needed_issues']}",
            f"- total_groups: {sync_retention['total_groups']}",
            f"- prunable_groups: {sync_retention['prunable_groups']}",
            f"- prunable_bytes: {sync_retention['prunable_bytes_human']}",
        ]
    )
    retention_entries = _list_of_dicts(sync_retention["entries"])
    if not retention_entries:
        lines.append("- No applied sync retention entries yet.")
    else:
        for entry in retention_entries:
            issue_label = entry["issue_id"] if entry["issue_id"] is not None else "unknown"
            lines.extend(
                [
                    "",
                    f"### {entry['tracker']} · issue #{issue_label}",
                    f"- status: {entry['status']}",
                    f"- integrity_findings: {entry['integrity_findings']}",
                    f"- keep_groups_limit: {entry['keep_groups_limit']}",
                    f"- groups: total={entry['total_groups']} kept={entry['kept_groups']} prunable={entry['prunable_groups']}",
                    f"- bytes: total={entry['total_bytes_human']} kept={entry['kept_bytes_human']} prunable={entry['prunable_bytes_human']}",
                    f"- ages: newest={entry['newest_group_age_human']} oldest={entry['oldest_group_age_human']} oldest_prunable={entry['oldest_prunable_group_age_human']}",
                ]
            )
            finding_codes = entry["finding_codes"]
            if finding_codes:
                lines.append(f"- finding_codes: {', '.join(str(code) for code in finding_codes)}")
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
            "## Ops snapshots",
            f"- status: {ops_snapshots['status']}",
            f"- history_entry_count: {ops_snapshots['history_entry_count']}",
            f"- history_limit: {ops_snapshots['history_limit']}",
            f"- dropped_entry_count: {ops_snapshots['dropped_entry_count']}",
            f"- archive_entry_count: {ops_snapshots['archive_entry_count']}",
        ]
    )
    latest_ops = _snapshot_mapping(ops_snapshots, "latest")
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
                f"  - brief_severity: {latest_ops.get('brief_severity', '-')}",
                f"  - brief_headline: {latest_ops.get('brief_headline', '-')}",
                f"  - landing_html: {latest_ops.get('landing_html', '-')}",
                f"  - brief_json: {latest_ops.get('brief_json', '-')}",
            ]
        )
    ops_entries = _list_of_dicts(ops_snapshots.get("entries"))
    if ops_entries:
        lines.append("- entries:")
        for entry in ops_entries:
            lines.append(
                f"  - {entry.get('entry_id', '-')}: status={entry.get('overall_status', '-')} "
                f"brief={entry.get('brief_severity', '-')} "
                f"age={entry.get('age_human', '-')} archive={entry.get('has_archive', False)}"
            )
    lines.extend(
        [
            "",
            "## Reports",
            f"- available_reports: {reports['total']}",
            f"- report_freshness_severity: {reports['freshness_severity']}",
            f"- report_summary_severity: {reports['report_summary_severity']}",
            f"- report_summary_reason: {reports['report_summary_severity_reason']}",
            f"- aging_reports: {reports['aging_total']}",
            f"- future_reports: {reports['future_total']}",
            f"- unknown_reports: {reports['unknown_total']}",
            f"- stale_reports: {reports['stale_total']}",
            f"- policy_drift_severity: {reports['policy_drift_severity']}",
            f"- policy_drift_reason: {reports['policy_drift_severity_reason']}",
            f"- policy_drift_reports: {reports['policy_drift_total']}",
            f"- policy_drift_guidance: {reports['policy_drift_guidance'] or 'n/a'}",
            f"- policy_embedded_reports: {reports['policy_embedded_total']}",
            f"- reports_without_embedded_policy: {reports['policy_missing_total']}",
            f"- reports_by_freshness: {_render_report_metrics(reports['freshness'])}",
            f"- cleanup_reports: {reports['cleanup_total']}",
            f"- cleanup_freshness_severity: {reports['cleanup_freshness_severity']}",
            f"- cleanup_aging_reports: {reports['cleanup_aging_total']}",
            f"- cleanup_future_reports: {reports['cleanup_future_total']}",
            f"- cleanup_unknown_reports: {reports['cleanup_unknown_total']}",
            f"- stale_cleanup_reports: {reports['cleanup_stale_total']}",
            f"- cleanup_reports_by_freshness: {_render_report_metrics(reports['cleanup_freshness'])}",
        ]
    )
    report_entries = _list_of_dicts(reports["entries"])
    if not report_entries:
        lines.append("- No report exports yet.")
    else:
        for entry in report_entries:
            related_report_detail_lines = _render_related_report_detail_lines(
                entry.get("details"),
                remediation=(
                    _string_or_none(reports.get("policy_drift_guidance"))
                    or _report_policy_drift_guidance_detail()
                ),
            )
            lines.extend(
                [
                    "",
                    f"### {entry['label']}",
                    f"- status: {entry['status']}",
                    f"- generated_at: {entry['generated_at'] or 'n/a'}",
                    f"- freshness: {entry['freshness_status']}",
                    f"- age: {entry['age_human']}",
                    f"- summary: {entry['summary']}",
                    f"- json_path: {entry['json_path'] or 'n/a'}",
                    f"- markdown_path: {entry['markdown_path'] or 'n/a'}",
                    f"- policy: {entry['policy_summary'] or 'n/a'}",
                    f"- policy_thresholds: {_render_report_metrics(entry['policy'])}",
                    f"- embedded_policy: {entry['embedded_policy_summary'] or 'n/a'}",
                    f"- embedded_policy_thresholds: {_render_report_metrics(entry['embedded_policy'])}",
                    f"- policy_alignment: {entry['policy_alignment_status']}",
                    f"- policy_alignment_note: {entry['policy_alignment_note']}",
                    f"- policy_alignment_remediation: {entry.get('policy_alignment_remediation') or 'n/a'}",
                    f"- metrics: {_render_report_metrics(entry['metrics'])}",
                    f"- details: {_render_report_details(entry['details'])}",
                    f"- related_cards: {_render_report_relations(entry['related_cards'])}",
                    f"- referenced_by: {_render_report_relations(entry['referenced_by'])}",
                ]
            )
            lines.extend(related_report_detail_lines)
    return "\n".join(lines) + "\n"


def _render_metric_card(
    label: str,
    value: str,
    *,
    tone: str | None = None,
    note: str | None = None,
) -> str:
    metric_id = "visible-runs-count" if label == "Visible runs" else ""
    id_attr = f' id="{metric_id}"' if metric_id else ""
    classes = ["metric-card"]
    if tone:
        classes.append(f"metric-card-{tone}")
    note_markup = f'<span class="metric-note">{escape(note)}</span>' if note else ""
    return (
        f'<article class="{" ".join(classes)}">'
        f'<span class="metric-label">{escape(label)}</span>'
        f'<span class="metric-value"{id_attr}>{escape(value)}</span>'
        f"{note_markup}"
        "</article>"
    )


def _render_hero_chip(chip: dict[str, object]) -> str:
    label = str(chip["label"])
    severity = str(chip["severity"])
    value = str(chip["value"])
    return (
        f'<span class="hero-chip status status-{escape(severity)}">'
        f"{escape(label)} · {escape(value)}"
        "</span>"
    )


def _render_run_card(run: dict[str, object]) -> str:
    artifact_links = [
        _render_token_link(str(artifact["label"]), _string_or_none(artifact["href"]))
        for artifact in _list_of_dicts(run["artifacts"])
    ]
    workspace_href = _string_or_none(run["workspace_href"])
    external_actions = _render_external_actions(_list_of_dicts(run["external_actions"]))
    status_value = str(run["status"])
    status_class = status_value.replace("_", "-")
    next_retry = ""
    if run["next_retry_at"]:
        next_retry = f"<li><strong>next retry:</strong> {escape(str(run['next_retry_at']))}</li>"

    return f"""
    <article class="run-card" data-status="{escape(status_value)}" data-search="{escape(str(run['search_index']))}">
      <div class="run-head">
        <div>
          <p class="run-subtitle">issue #{run['issue_id']} · run {escape(str(run['run_id']))}</p>
          <h2 class="run-title">{escape(str(run['issue_title']))}</h2>
        </div>
        <span class="status status-{status_class}">{escape(status_value)}</span>
      </div>
      <div class="run-grid">
        <section class="panel">
          <h3>Summary</h3>
          <p class="copy">{escape(str(run['summary'] or "No summary recorded."))}</p>
          {f'<p class="copy error">{escape(str(run["last_error"]))}</p>' if run["last_error"] else ''}
        </section>
        <section class="panel">
          <h3>Runtime</h3>
          <ul class="list">
            <li><strong>backend:</strong> {escape(str(run['backend_mode']))}</li>
            <li><strong>attempts:</strong> {run['attempts']}</li>
            <li><strong>updated:</strong> {escape(str(run['updated_at']))}</li>
            <li><strong>role:</strong> {escape(str(run['current_role'] or "-"))}</li>
            {next_retry}
          </ul>
        </section>
      </div>
      <div class="run-grid">
        <section class="panel">
          <h3>Artifacts</h3>
          <div class="token-row">
            {"".join(artifact_links) if artifact_links else '<span class="token">none</span>'}
          </div>
        </section>
        <section class="panel">
          <h3>Workspace</h3>
          <div class="token-row">
            {_render_token_link("workspace", workspace_href) if workspace_href else '<span class="token">none</span>'}
          </div>
        </section>
      </div>
      <section class="panel" style="margin-top: 1rem;">
        <h3>External actions</h3>
        {external_actions}
      </section>
    </article>
    """


def _render_sync_handoff_card(handoff: dict[str, object]) -> str:
    issue_label = handoff["issue_id"] if handoff["issue_id"] is not None else "unknown"
    primary_links = [
        _render_token_link("manifest", _string_or_none(handoff["manifest_href"])),
        _render_token_link("archive", _string_or_none(handoff["archived_href"])),
    ]
    source_href = _string_or_none(handoff["source_href"])
    if source_href:
        primary_links.append(_render_token_link("source", source_href))

    normalized_link_tokens = [
        _render_token_link(str(link["label"]), _string_or_none(link["href"]))
        for link in _list_of_dicts(handoff["normalized_links"])
    ]
    refs = _snapshot_mapping(handoff, "refs")
    ref_items = [
        f"<li><strong>{escape(str(key))}:</strong> {escape(str(value))}</li>"
        for key, value in sorted(refs.items())
        if value not in (None, "")
    ]
    handoff_info = _snapshot_mapping(handoff, "handoff")

    return f"""
    <article class="handoff-card">
      <div class="run-head">
        <div>
          <p class="run-subtitle">{escape(str(handoff['tracker']))} · issue #{escape(str(issue_label))} · {escape(str(handoff['action']))}</p>
          <h2 class="run-title">{escape(str(handoff['artifact_role'] or handoff['action']))}</h2>
        </div>
        <span class="status status-sync">sync</span>
      </div>
      <div class="run-grid">
        <section class="panel">
          <h3>Summary</h3>
          <p class="copy">{escape(str(handoff['summary'] or "No summary recorded."))}</p>
        </section>
        <section class="panel">
          <h3>Metadata</h3>
          <ul class="list">
            <li><strong>applied:</strong> {escape(str(handoff['applied_at']))}</li>
            <li><strong>staged:</strong> {escape(str(handoff['staged_at'] or "-"))}</li>
            <li><strong>issue_key:</strong> {escape(str(handoff['issue_key'] or "-"))}</li>
            <li><strong>bundle_key:</strong> {escape(str(handoff['bundle_key'] or "-"))}</li>
            <li><strong>group:</strong> {escape(str(handoff_info.get('group_key') or "-"))} ({handoff_info.get('group_index', 0) + 1}/{handoff_info.get('group_size', 0)})</li>
          </ul>
        </section>
      </div>
      <div class="run-grid">
        <section class="panel">
          <h3>Tracked links</h3>
          <div class="token-row">
            {"".join(primary_links) if primary_links else '<span class="token">none</span>'}
          </div>
          <div class="token-row" style="margin-top: 0.7rem;">
            {"".join(normalized_link_tokens) if normalized_link_tokens else '<span class="token">no normalized links</span>'}
          </div>
        </section>
        <section class="panel">
          <h3>Refs</h3>
          {f'<ul class="list">{"".join(ref_items)}</ul>' if ref_items else '<p class="copy">No refs recorded.</p>'}
        </section>
      </div>
    </article>
    """


def _render_sync_retention_issue_card(entry: dict[str, object]) -> str:
    issue_label = entry["issue_id"] if entry["issue_id"] is not None else "unknown"
    status_value = str(entry["status"])
    groups = _list_of_dicts(entry["groups"])
    group_items = []
    for group in groups[:4]:
        group_items.append(
            "<li>"
            f"<strong>{escape(str(group['status']))}</strong> · "
            f"{escape(str(group['group_key']))} · "
            f"size {escape(str(group['total_bytes_human']))} · "
            f"newest {escape(str(group['newest_age_human']))} · "
            f"actions {escape(', '.join(str(action) for action in group['actions']) or 'none')}"
            "</li>"
        )
    links = [
        _render_token_link("manifest", _string_or_none(entry["manifest_href"])),
        _render_token_link("issue archive", _string_or_none(entry["issue_root_href"])),
    ]
    finding_codes = entry["finding_codes"]
    return f"""
    <article class="retention-card">
      <div class="run-head">
        <div>
          <p class="run-subtitle">{escape(str(entry['tracker']))} · issue #{escape(str(issue_label))}</p>
          <h2 class="run-title">Retention posture</h2>
        </div>
        <span class="status status-{escape(status_value)}">{escape(status_value)}</span>
      </div>
      <div class="run-grid">
        <section class="panel">
          <h3>Summary</h3>
          <ul class="list">
            <li><strong>groups:</strong> {entry['kept_groups']}/{entry['total_groups']} kept, {entry['prunable_groups']} prunable</li>
            <li><strong>bytes:</strong> {escape(str(entry['kept_bytes_human']))} kept, {escape(str(entry['prunable_bytes_human']))} prunable</li>
            <li><strong>ages:</strong> newest {escape(str(entry['newest_group_age_human']))}, oldest {escape(str(entry['oldest_group_age_human']))}</li>
            <li><strong>oldest prunable:</strong> {escape(str(entry['oldest_prunable_group_age_human']))}</li>
          </ul>
        </section>
        <section class="panel">
          <h3>Integrity</h3>
          <p class="copy">{escape(str(entry['integrity_findings']))} finding(s)</p>
          {f'<p class="copy error">{escape(", ".join(str(code) for code in finding_codes))}</p>' if finding_codes else '<p class="copy">No integrity findings recorded.</p>'}
          <div class="token-row" style="margin-top: 0.7rem;">
            {"".join(links)}
          </div>
        </section>
      </div>
      <section class="panel" style="margin-top: 1rem;">
        <h3>Group samples</h3>
        {f'<ul class="group-list">{"".join(group_items)}</ul>' if group_items else '<p class="copy">No eligible groups recorded.</p>'}
      </section>
    </article>
    """


def _render_report_card(entry: dict[str, object]) -> str:
    status_value = str(entry["status"])
    card_anchor = str(entry["card_anchor"])
    links = [
        _render_token_link("json", _string_or_none(entry["json_href"])),
        _render_token_link("markdown", _string_or_none(entry["markdown_href"])),
    ]
    metrics = _snapshot_mapping(entry, "metrics")
    details = _snapshot_mapping(entry, "details")
    related_cards = _list_of_dicts(entry["related_cards"])
    referenced_by = _list_of_dicts(entry["referenced_by"])
    policy_summary = _string_or_none(entry.get("policy_summary")) or "n/a"
    embedded_policy_summary = _string_or_none(entry.get("embedded_policy_summary")) or "n/a"
    policy_alignment_status = _string_or_none(entry.get("policy_alignment_status")) or "missing"
    policy_alignment_note = _string_or_none(entry.get("policy_alignment_note")) or "n/a"
    policy_alignment_remediation = _string_or_none(entry.get("policy_alignment_remediation"))
    policy = entry.get("policy")
    if not isinstance(policy, dict):
        policy = {}
    embedded_policy = entry.get("embedded_policy")
    if not isinstance(embedded_policy, dict):
        embedded_policy = {}
    metric_items = [
        f"<li><strong>{escape(str(key))}:</strong> {escape(str(value))}</li>"
        for key, value in sorted(metrics.items())
        if value not in (None, "", [])
    ]
    detail_items = _render_report_detail_items(details)
    policy_items = [
        f"<li><strong>{escape(str(key))}:</strong> {escape(str(value))}</li>"
        for key, value in sorted(policy.items())
        if value not in (None, "", [])
    ]
    embedded_policy_items = [
        f"<li><strong>{escape(str(key))}:</strong> {escape(str(value))}</li>"
        for key, value in sorted(embedded_policy.items())
        if value not in (None, "", [])
    ]
    related_links = [
        _render_token_link(str(item["label"]), _string_or_none(item["card_href"]))
        for item in related_cards
    ]
    referenced_links = [
        _render_token_link(str(item["label"]), _string_or_none(item["card_href"]))
        for item in referenced_by
    ]
    related_detail_markup = _render_related_report_detail_html(details)
    freshness_line = (
        f'<p class="run-subtitle" style="margin-top: 0.35rem;">freshness {escape(str(entry["freshness_status"]))} · age {escape(str(entry["age_human"]))}</p>'
        if entry["freshness_status"] != "unknown"
        else ""
    )
    return f"""
    <article id="{escape(card_anchor)}" class="report-card">
      <div class="run-head">
        <div>
          <p class="run-subtitle">report export</p>
          <h2 class="run-title">{escape(str(entry['label']))}</h2>
        </div>
        <span class="status status-{escape(status_value)}">{escape(status_value)}</span>
      </div>
      <div class="run-grid">
        <section class="panel">
          <h3>Summary</h3>
          <p class="copy">{escape(str(entry['summary']))}</p>
          <p class="run-subtitle" style="margin-top: 0.7rem;">generated_at {escape(str(entry['generated_at'] or "n/a"))}</p>
          {freshness_line}
        </section>
        <section class="panel">
          <h3>Links</h3>
          <div class="token-row">
            {"".join(links)}
          </div>
        </section>
      </div>
      <section class="panel" style="margin-top: 1rem;">
        <h3>Metrics</h3>
        {f'<ul class="list">{"".join(metric_items)}</ul>' if metric_items else '<p class="copy">No metrics recorded.</p>'}
      </section>
      <section class="panel" style="margin-top: 1rem;">
        <h3>Details</h3>
        {f'<ul class="list">{"".join(detail_items)}</ul>' if detail_items else '<p class="copy">No extra details recorded.</p>'}
      </section>
      <section class="panel" style="margin-top: 1rem;">
        <h3>Policy context</h3>
        <p class="copy">{escape(policy_summary)}</p>
        {f'<ul class="list" style="margin-top: 0.7rem;">{"".join(policy_items)}</ul>' if policy_items else '<p class="copy">No policy thresholds recorded.</p>'}
        <p class="run-subtitle" style="margin-top: 0.8rem;">embedded policy {escape(policy_alignment_status)}</p>
        <p class="copy{' error' if policy_alignment_status == 'drift' else ''}">{escape(embedded_policy_summary)}</p>
        <p class="copy{' error' if policy_alignment_status == 'drift' else ''}">{escape(policy_alignment_note)}</p>
        {f'<p class="copy">{escape(policy_alignment_remediation)}</p>' if policy_alignment_remediation else ''}
        {f'<ul class="list" style="margin-top: 0.7rem;">{"".join(embedded_policy_items)}</ul>' if embedded_policy_items else '<p class="copy">No embedded policy thresholds recorded.</p>'}
      </section>
      <section class="panel" style="margin-top: 1rem;">
        <h3>Cross references</h3>
        <p class="run-subtitle">related reports</p>
        <div class="token-row">
          {"".join(related_links) if related_links else '<span class="token">none</span>'}
        </div>
        {related_detail_markup}
        <p class="run-subtitle" style="margin-top: 0.8rem;">referenced by</p>
        <div class="token-row">
          {"".join(referenced_links) if referenced_links else '<span class="token">none</span>'}
        </div>
      </section>
    </article>
    """


def _render_ops_snapshot_section(snapshot: dict[str, object]) -> str:
    if snapshot["status"] == "missing":
        return """
        <article class="empty-state">
          <h2>No ops snapshots yet</h2>
          <p>Run <code>repoagents ops snapshot</code> to publish latest/history bundle metadata into this dashboard.</p>
        </article>
        """
    latest = _snapshot_mapping(snapshot, "latest")
    entries = _list_of_dicts(snapshot.get("entries"))
    latest_links = [
        _render_token_link("latest json", _string_or_none(snapshot.get("latest_json_href"))),
        _render_token_link("latest markdown", _string_or_none(snapshot.get("latest_markdown_href"))),
        _render_token_link("history json", _string_or_none(snapshot.get("history_json_href"))),
        _render_token_link("history markdown", _string_or_none(snapshot.get("history_markdown_href"))),
    ]
    landing_html_href = _string_or_none(latest.get("landing_html_href"))
    if landing_html_href:
        latest_links.append(_render_token_link("landing html", landing_html_href))
    landing_markdown_href = _string_or_none(latest.get("landing_markdown_href"))
    if landing_markdown_href:
        latest_links.append(_render_token_link("landing md", landing_markdown_href))
    brief_json_href = _string_or_none(latest.get("brief_json_href"))
    if brief_json_href:
        latest_links.append(_render_token_link("brief json", brief_json_href))
    brief_markdown_href = _string_or_none(latest.get("brief_markdown_href"))
    if brief_markdown_href:
        latest_links.append(_render_token_link("brief md", brief_markdown_href))
    archive_href = _string_or_none(latest.get("archive_href"))
    if archive_href:
        latest_links.append(_render_token_link("archive", archive_href))
    component_statuses = latest.get("component_statuses")
    if not isinstance(component_statuses, dict):
        component_statuses = {}
    component_items = [
        f"<li><strong>{escape(str(name))}:</strong> {escape(str(status))}</li>"
        for name, status in sorted(component_statuses.items())
    ]
    history_items = []
    for entry in entries:
        links = [
            _render_token_link("bundle", _string_or_none(entry.get("bundle_json_href"))),
        ]
        archive_entry_href = _string_or_none(entry.get("archive_href"))
        if archive_entry_href:
            links.append(_render_token_link("archive", archive_entry_href))
        history_items.append(
            "<li>"
            f"<strong>{escape(str(entry['entry_id']))}</strong> · "
            f"status {escape(str(entry['overall_status']))} · "
            f"brief {escape(str(entry.get('brief_severity', 'unknown')))} · "
            f"age {escape(str(entry['age_human']))} · "
            f"archive {'yes' if entry['has_archive'] else 'no'}"
            f'<p class="copy" style="margin-top: 0.5rem;">{escape(str(entry.get("brief_headline", "n/a")))}</p>'
            f'<div class="token-row" style="margin-top: 0.5rem;">{"".join(links)}</div>'
            "</li>"
        )
    latest_status = _string_or_none(latest.get("overall_status")) or "attention"
    return f"""
    <article class="report-card">
      <div class="run-head">
        <div>
          <p class="run-subtitle">ops bundle index</p>
          <h2 class="run-title">Latest ops snapshot</h2>
        </div>
        <span class="status status-{escape(latest_status)}">{escape(latest_status)}</span>
      </div>
      <div class="run-grid">
        <section class="panel">
          <h3>Latest</h3>
          <ul class="list">
            <li><strong>entry_id:</strong> {escape(str(latest.get('entry_id', '-')))}</li>
            <li><strong>rendered_at:</strong> {escape(str(latest.get('rendered_at', '-')))}</li>
            <li><strong>age:</strong> {escape(str(latest.get('age_human', '-')))}</li>
            <li><strong>bundle_dir:</strong> {escape(str(latest.get('bundle_dir', '-')))}</li>
            <li><strong>archive:</strong> {escape(str(latest.get('archive_path', '-')))}</li>
            <li><strong>brief:</strong> {escape(str(latest.get('brief_headline', '-')))}</li>
            <li><strong>brief status:</strong> {escape(str(latest.get('brief_severity', '-')))}</li>
          </ul>
          <div class="token-row" style="margin-top: 0.7rem;">
            {"".join(latest_links)}
          </div>
        </section>
        <section class="panel">
          <h3>Component statuses</h3>
          {f'<ul class="list">{"".join(component_items)}</ul>' if component_items else '<p class="copy">No component statuses recorded.</p>'}
        </section>
      </div>
      <section class="panel" style="margin-top: 1rem;">
        <h3>Indexed history</h3>
        <p class="copy">Showing {len(entries)} of {snapshot['history_entry_count']} indexed ops snapshots. History limit is {snapshot['history_limit']}.</p>
        {f'<ul class="group-list">{"".join(history_items)}</ul>' if history_items else '<p class="copy">No indexed ops snapshot entries recorded.</p>'}
      </section>
    </article>
    """


def _render_external_actions(actions: list[dict[str, object]]) -> str:
    if not actions:
        return '<p class="copy">No external actions recorded.</p>'
    items = []
    for action in actions:
        label = f"{action['action']} · executed={action['executed']}"
        link = _string_or_none(action["href"])
        body = escape(str(action["reason"]))
        if link:
            items.append(
                f'<li><a href="{escape(link)}">{escape(label)}</a><br /><span class="copy">{body}</span></li>'
            )
        else:
            items.append(f"<li>{escape(label)}<br /><span class=\"copy\">{body}</span></li>")
    return f'<ul class="list">{"".join(items)}</ul>'


def _render_link_chip(label: str, href: str | None) -> str:
    if not href:
        return f'<span class="meta-chip">{escape(label)}</span>'
    return f'<a class="link-chip" href="{escape(href)}">{escape(label)}</a>'


def _render_token_link(label: str, href: str | None) -> str:
    if not href:
        return f'<span class="token">{escape(label)}</span>'
    return f'<a class="token" href="{escape(href)}">{escape(label)}</a>'


def _payload_href(output_path: Path, value: str) -> str | None:
    if value.startswith(("http://", "https://")):
        return value
    return _relative_href(output_path, Path(value))


def _relative_href(output_path: Path, target: Path) -> str | None:
    base_dir = output_path.parent.resolve()
    target_path = target.resolve()
    relative = os.path.relpath(target_path, start=base_dir)
    return quote(Path(relative).as_posix(), safe="/#:=?&-._")


def _serialize_run_record(
    loaded: LoadedConfig,
    record: RunRecord,
    output_path: Path,
) -> dict[str, object]:
    artifact_dir = loaded.artifacts_dir / f"issue-{record.issue_id}" / record.run_id
    artifacts = [
        {
            "label": "artifacts",
            "path": str(artifact_dir),
            "href": _relative_href(output_path, artifact_dir),
        }
    ]
    for role_name, artifact_path in sorted(record.role_artifacts.items()):
        artifacts.append(
            {
                "label": role_name,
                "path": artifact_path,
                "href": _relative_href(output_path, Path(artifact_path)),
            }
        )
    external_actions = []
    for action in record.external_actions:
        payload = action.payload
        link = None
        for key in ("url", "path", "stage_path"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                link = _payload_href(output_path, value)
                break
        external_actions.append(
            {
                **action.model_dump(mode="json"),
                "href": link,
            }
        )
    search_index = " ".join(
        value.lower()
        for value in (
            record.issue_title,
            record.run_id,
            record.summary or "",
            record.last_error or "",
            record.current_role or "",
            record.backend_mode,
            str(record.issue_id),
            record.status.value,
        )
        if value
    )
    return {
        "issue_id": record.issue_id,
        "issue_title": record.issue_title,
        "run_id": record.run_id,
        "status": record.status.value,
        "backend_mode": record.backend_mode,
        "summary": record.summary,
        "last_error": record.last_error,
        "current_role": record.current_role,
        "attempts": record.attempts,
        "updated_at": record.updated_at.isoformat(),
        "next_retry_at": record.next_retry_at.isoformat() if record.next_retry_at else None,
        "workspace_path": record.workspace_path,
        "workspace_href": (
            _relative_href(output_path, Path(record.workspace_path)) if record.workspace_path else None
        ),
        "artifacts": artifacts,
        "external_actions": external_actions,
        "search_index": search_index,
    }


def _load_sync_handoffs(
    *,
    loaded: LoadedConfig,
    output_path: Path,
    limit: int,
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    if not loaded.sync_applied_dir.exists():
        return {"total": 0, "entries": entries}

    for manifest_path in sorted(loaded.sync_applied_dir.glob("*/issue-*/manifest.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, list):
            continue
        source_archive_map = {
            source_relative_path: archived_relative_path
            for entry in payload
            if isinstance(entry, dict)
            for source_relative_path, archived_relative_path in [
                (
                    _string_or_none(entry.get("source_relative_path")),
                    _string_or_none(entry.get("archived_relative_path")),
                )
            ]
            if source_relative_path and archived_relative_path
        }
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            entries.append(
                _serialize_sync_handoff_entry(
                    loaded=loaded,
                    output_path=output_path,
                    manifest_path=manifest_path,
                    entry=entry,
                    source_archive_map=source_archive_map,
                )
            )

    entries.sort(
        key=lambda item: (
            str(item["applied_at"] or ""),
            str(item["tracker"]),
            str(item["issue_id"] if item["issue_id"] is not None else ""),
            str(item["action"]),
        ),
        reverse=True,
    )
    return {"total": len(entries), "entries": entries[:limit]}


def _load_report_summaries(
    *,
    loaded: LoadedConfig,
    output_path: Path,
    rendered_at: str,
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for key, label, json_name, markdown_name in REPORT_EXPORTS:
        json_path = loaded.reports_dir / json_name
        markdown_path = loaded.reports_dir / markdown_name
        if not json_path.exists() and not markdown_path.exists():
            continue
        payload = _load_report_payload(json_path) if json_path.exists() else None
        entries.append(
            _serialize_report_entry(
                output_path=output_path,
                key=key,
                label=label,
                json_path=json_path if json_path.exists() else None,
                markdown_path=markdown_path if markdown_path.exists() else None,
                payload=payload,
                rendered_at=rendered_at,
            )
        )
    _attach_report_cross_references(entries)
    policy_snapshot = _build_report_freshness_policy_snapshot(loaded)
    _attach_report_policy_context(entries, policy_snapshot)
    _attach_related_report_detail_summaries(entries)
    report_freshness = _count_report_freshness(entries)
    cleanup_freshness = _count_report_freshness(entries, key_prefix="cleanup-")
    policy = loaded.data.dashboard.report_freshness_policy
    freshness_severity, freshness_severity_reason = _report_freshness_severity(
        report_freshness,
        unknown_issues_threshold=policy.unknown_issues_threshold,
        stale_issues_threshold=policy.stale_issues_threshold,
        future_attention_threshold=policy.future_attention_threshold,
        aging_attention_threshold=policy.aging_attention_threshold,
    )
    cleanup_freshness_severity, cleanup_freshness_severity_reason = _report_freshness_severity(
        cleanup_freshness,
        unknown_issues_threshold=policy.unknown_issues_threshold,
        stale_issues_threshold=policy.stale_issues_threshold,
        future_attention_threshold=policy.future_attention_threshold,
        aging_attention_threshold=policy.aging_attention_threshold,
    )
    policy_alignment_counts = _count_report_policy_alignment(entries)
    policy_drift_severity, policy_drift_severity_reason = _report_policy_drift_severity(
        policy_alignment_counts["drift"]
    )
    report_summary_severity, report_summary_severity_reason = _combine_report_summary_severity(
        freshness_severity=freshness_severity,
        freshness_reason=freshness_severity_reason,
        policy_drift_severity=policy_drift_severity,
        policy_drift_reason=policy_drift_severity_reason,
    )
    return {
        "total": len(entries),
        "aging_total": report_freshness.get("aging", 0),
        "future_total": report_freshness.get("future", 0),
        "unknown_total": report_freshness.get("unknown", 0),
        "stale_total": report_freshness.get("stale", 0),
        "freshness": report_freshness,
        "freshness_severity": freshness_severity,
        "freshness_severity_reason": freshness_severity_reason,
        "report_summary_severity": report_summary_severity,
        "report_summary_severity_reason": report_summary_severity_reason,
        "cleanup_total": sum(cleanup_freshness.values()),
        "cleanup_aging_total": cleanup_freshness.get("aging", 0),
        "cleanup_future_total": cleanup_freshness.get("future", 0),
        "cleanup_unknown_total": cleanup_freshness.get("unknown", 0),
        "cleanup_stale_total": cleanup_freshness.get("stale", 0),
        "cleanup_freshness": cleanup_freshness,
        "cleanup_freshness_severity": cleanup_freshness_severity,
        "cleanup_freshness_severity_reason": cleanup_freshness_severity_reason,
        "policy_drift_severity": policy_drift_severity,
        "policy_drift_severity_reason": policy_drift_severity_reason,
        "policy_drift_guidance": (
            _report_policy_drift_guidance_detail()
            if policy_alignment_counts["drift"] > 0
            else None
        ),
        "policy_drift_total": policy_alignment_counts["drift"],
        "policy_embedded_total": policy_alignment_counts["embedded"],
        "policy_missing_total": policy_alignment_counts["missing"],
        "entries": entries,
    }


def _load_ops_snapshot_summaries(
    *,
    loaded: LoadedConfig,
    output_path: Path,
    rendered_at: str,
) -> dict[str, object]:
    ops_root = loaded.reports_dir / "ops"
    latest_json = ops_root / "latest.json"
    latest_markdown = ops_root / "latest.md"
    history_json = ops_root / "history.json"
    history_markdown = ops_root / "history.md"
    latest_payload = _load_report_payload(latest_json) if latest_json.exists() else None
    history_payload = _load_report_payload(history_json) if history_json.exists() else None
    if latest_payload is None and history_payload is None:
        return {
            "status": "missing",
            "history_entry_count": 0,
            "history_limit": 0,
            "dropped_entry_count": 0,
            "archive_entry_count": 0,
            "latest_json_path": None,
            "latest_json_href": None,
            "latest_markdown_path": None,
            "latest_markdown_href": None,
            "history_json_path": None,
            "history_json_href": None,
            "history_markdown_path": None,
            "history_markdown_href": None,
            "latest": {},
            "entries": [],
        }
    latest_entry = _dict_value(latest_payload or {}, "latest")
    history_meta = _dict_value(history_payload or {}, "meta")
    raw_history_entries = (history_payload or {}).get("entries")
    if not isinstance(raw_history_entries, list):
        raw_history_entries = []
    history_entries = [
        _serialize_ops_snapshot_entry(
            entry=entry,
            output_path=output_path,
            rendered_at=rendered_at,
        )
        for entry in raw_history_entries
        if isinstance(entry, dict)
    ]
    latest = (
        _serialize_ops_snapshot_entry(
            entry=latest_entry,
            output_path=output_path,
            rendered_at=rendered_at,
        )
        if latest_entry
        else {}
    )
    return {
        "status": "available",
        "history_entry_count": int(history_meta.get("entry_count", len(history_entries)) or 0),
        "history_limit": int(history_meta.get("history_limit", 0) or 0),
        "dropped_entry_count": int(history_meta.get("dropped_entry_count", 0) or 0),
        "archive_entry_count": sum(1 for entry in history_entries if entry.get("has_archive")),
        "latest_json_path": str(latest_json) if latest_json.exists() else None,
        "latest_json_href": _relative_href(output_path, latest_json) if latest_json.exists() else None,
        "latest_markdown_path": str(latest_markdown) if latest_markdown.exists() else None,
        "latest_markdown_href": _relative_href(output_path, latest_markdown) if latest_markdown.exists() else None,
        "history_json_path": str(history_json) if history_json.exists() else None,
        "history_json_href": _relative_href(output_path, history_json) if history_json.exists() else None,
        "history_markdown_path": str(history_markdown) if history_markdown.exists() else None,
        "history_markdown_href": _relative_href(output_path, history_markdown) if history_markdown.exists() else None,
        "latest": latest,
        "entries": history_entries[:OPS_SNAPSHOT_ENTRY_PREVIEW_LIMIT],
    }


def _serialize_ops_snapshot_entry(
    *,
    entry: dict[str, object],
    output_path: Path,
    rendered_at: str,
) -> dict[str, object]:
    rendered_value = _string_or_none(entry.get("rendered_at"))
    age_seconds, age_human, _ = _report_age_snapshot(
        rendered_at=rendered_at,
        generated_at=rendered_value,
    )
    archive = entry.get("archive")
    archive_path = None
    if isinstance(archive, dict):
        archive_path = _string_or_none(archive.get("path"))
    bundle_json = _string_or_none(entry.get("bundle_json"))
    bundle_markdown = _string_or_none(entry.get("bundle_markdown"))
    landing_html = _string_or_none(entry.get("landing_html"))
    landing_markdown = _string_or_none(entry.get("landing_markdown"))
    brief_json = _string_or_none(entry.get("brief_json"))
    brief_markdown = _string_or_none(entry.get("brief_markdown"))
    return {
        "entry_id": _string_or_none(entry.get("entry_id")) or "unknown",
        "rendered_at": rendered_value or "n/a",
        "age_seconds": age_seconds,
        "age_human": age_human,
        "overall_status": _string_or_none(entry.get("overall_status")) or "attention",
        "brief_severity": _string_or_none(entry.get("brief_severity")) or "unknown",
        "brief_headline": _string_or_none(entry.get("brief_headline")) or "n/a",
        "brief_top_finding_count": int(entry.get("brief_top_finding_count", 0) or 0),
        "brief_next_action_count": int(entry.get("brief_next_action_count", 0) or 0),
        "bundle_dir": _string_or_none(entry.get("bundle_dir")) or "n/a",
        "bundle_relative_dir": _string_or_none(entry.get("bundle_relative_dir")) or "n/a",
        "bundle_json": bundle_json,
        "bundle_json_href": _payload_href(output_path, bundle_json) if bundle_json else None,
        "bundle_markdown": bundle_markdown,
        "bundle_markdown_href": _payload_href(output_path, bundle_markdown) if bundle_markdown else None,
        "landing_html": landing_html,
        "landing_html_href": _payload_href(output_path, landing_html) if landing_html else None,
        "landing_markdown": landing_markdown,
        "landing_markdown_href": _payload_href(output_path, landing_markdown) if landing_markdown else None,
        "brief_json": brief_json,
        "brief_json_href": _payload_href(output_path, brief_json) if brief_json else None,
        "brief_markdown": brief_markdown,
        "brief_markdown_href": _payload_href(output_path, brief_markdown) if brief_markdown else None,
        "archive_path": archive_path,
        "archive_href": _payload_href(output_path, archive_path) if archive_path else None,
        "has_archive": bool(archive_path),
        "component_statuses": dict(_dict_value(entry, "component_statuses")),
    }


def _load_report_payload(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _dict_value(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _serialize_report_entry(
    *,
    output_path: Path,
    key: str,
    label: str,
    json_path: Path | None,
    markdown_path: Path | None,
    payload: dict[str, object] | None,
    rendered_at: str,
) -> dict[str, object]:
    status = "available"
    generated_at: str | None = None
    age_seconds: int | None = None
    age_human = "n/a"
    freshness_status = "unknown"
    summary = "Report export available."
    metrics: dict[str, object] = {}
    details: dict[str, object] = {}
    relation_specs: list[dict[str, object]] = []
    if payload is None and json_path is not None:
        status = "invalid"
        summary = "Report JSON could not be parsed."
    elif payload is not None:
        meta = payload.get("meta")
        if isinstance(meta, dict):
            generated_at = _string_or_none(meta.get("rendered_at"))
        report_summary = payload.get("summary")
        if isinstance(report_summary, dict):
            status, summary, metrics = _report_summary_details(key, report_summary)
        details = _report_details(key, payload)
        if key == "sync-audit":
            mismatch_count = details.get("cleanup_report_mismatches")
            if isinstance(mismatch_count, int):
                existing_mismatch_count = metrics.get("cleanup_report_mismatches")
                if not isinstance(existing_mismatch_count, int) or existing_mismatch_count < mismatch_count:
                    metrics["cleanup_report_mismatches"] = mismatch_count
        relation_specs = _report_relation_specs(key, payload)
    age_seconds, age_human, freshness_status = _report_age_snapshot(
        rendered_at=rendered_at,
        generated_at=generated_at,
    )
    card_anchor = f"report-{key}"
    return {
        "key": key,
        "label": label,
        "status": status,
        "generated_at": generated_at,
        "age_seconds": age_seconds,
        "age_human": age_human,
        "freshness_status": freshness_status,
        "summary": summary,
        "metrics": metrics,
        "details": details,
        "card_anchor": card_anchor,
        "card_href": f"#{card_anchor}",
        "relation_specs": relation_specs,
        "related_cards": [],
        "referenced_by": [],
        "policy_summary": None,
        "policy": {},
        "embedded_policy_summary": _extract_report_policy_summary(payload),
        "embedded_policy": _extract_report_policy_thresholds(payload),
        "policy_alignment_status": "missing",
        "policy_alignment_note": "raw report export did not embed policy metadata",
        "policy_alignment_remediation": None,
        "related_report_detail_summary": None,
        "json_path": str(json_path) if json_path else None,
        "json_href": _relative_href(output_path, json_path) if json_path else None,
        "markdown_path": str(markdown_path) if markdown_path else None,
        "markdown_href": _relative_href(output_path, markdown_path) if markdown_path else None,
    }


def _attach_report_policy_context(
    entries: list[dict[str, object]],
    policy_snapshot: dict[str, object],
) -> None:
    summary = _string_or_none(policy_snapshot.get("summary"))
    thresholds = policy_snapshot.get("report_freshness_policy")
    if not isinstance(thresholds, dict):
        thresholds = {}
    remediation_detail = _report_policy_drift_guidance_detail()
    for entry in entries:
        entry["policy_summary"] = summary
        entry["policy"] = dict(thresholds)
        embedded_summary = _string_or_none(entry.get("embedded_policy_summary"))
        if embedded_summary is None:
            entry["policy_alignment_status"] = "missing"
            entry["policy_alignment_note"] = "raw report export did not embed policy metadata"
            entry["policy_alignment_remediation"] = None
        elif embedded_summary == summary:
            entry["policy_alignment_status"] = "match"
            entry["policy_alignment_note"] = "embedded policy matches current config"
            entry["policy_alignment_remediation"] = None
        else:
            entry["policy_alignment_status"] = "drift"
            entry["policy_alignment_note"] = (
                f"embedded policy differs from current config ({embedded_summary})"
            )
            entry["policy_alignment_remediation"] = remediation_detail


def _attach_related_report_detail_summaries(entries: list[dict[str, object]]) -> None:
    remediation_detail = _report_policy_drift_guidance_detail()
    for entry in entries:
        entry["related_report_detail_summary"] = _build_related_report_detail_summary(
            entry.get("details"),
            remediation=remediation_detail,
        )


def _report_summary_details(
    key: str,
    report_summary: dict[str, object],
) -> tuple[str, str, dict[str, object]]:
    if key == "ops-brief":
        status = _string_or_none(report_summary.get("severity")) or "available"
        headline = _string_or_none(report_summary.get("headline")) or "ops brief available"
        summary = headline
        metrics = {
            "top_finding_count": int(report_summary.get("top_finding_count", 0) or 0),
            "next_action_count": int(report_summary.get("next_action_count", 0) or 0),
            "selected_runs": report_summary.get("selected_runs", 0),
            "report_health_severity": report_summary.get("report_health_severity", "unknown"),
            "sync_audit_status": report_summary.get("sync_audit_status", "unknown"),
            "sync_health_status": report_summary.get("sync_health_status", "unknown"),
            "github_smoke_status": report_summary.get("github_smoke_status", "not_applicable"),
        }
        return status, summary, metrics
    if key == "sync-health":
        status = _string_or_none(report_summary.get("overall_status")) or "available"
        pending = report_summary.get("pending_artifacts", 0)
        integrity = report_summary.get("integrity_issue_count", 0)
        cleanup_actions = report_summary.get("cleanup_action_count", 0)
        summary = (
            f"pending={pending} integrity_issues={integrity} cleanup_actions={cleanup_actions}"
        )
        metrics = {
            "pending_artifacts": pending,
            "integrity_issue_count": integrity,
            "repair_changed_reports": report_summary.get("repair_changed_reports", 0),
            "repair_findings_after": report_summary.get("repair_findings_after", 0),
            "cleanup_action_count": cleanup_actions,
            "cleanup_sync_applied_action_count": report_summary.get(
                "cleanup_sync_applied_action_count",
                0,
            ),
            "prunable_groups": report_summary.get("prunable_groups", 0),
            "repair_needed_issues": report_summary.get("repair_needed_issues", 0),
            "related_cleanup_reports": report_summary.get("related_cleanup_reports", 0),
            "related_sync_audit_reports": report_summary.get("related_sync_audit_reports", 0),
            "related_report_mismatches": report_summary.get("related_report_mismatches", 0),
            "related_report_policy_drifts": report_summary.get("related_report_policy_drifts", 0),
            "next_action_count": len(_list_of_strings(report_summary.get("next_actions"))),
        }
        return status, summary, metrics
    if key == "github-smoke":
        status = _string_or_none(report_summary.get("status")) or "available"
        open_issue_count = report_summary.get("open_issue_count", 0)
        sampled_issue_id = report_summary.get("sampled_issue_id")
        summary = (
            f"open_issues={open_issue_count} "
            f"publish={report_summary.get('publish_status', 'unknown')} "
            f"branch_policy={report_summary.get('branch_policy_status', 'unknown')}"
        )
        metrics = {
            "open_issue_count": open_issue_count,
            "sampled_issue_id": sampled_issue_id,
            "repo_access_status": report_summary.get("repo_access_status", "unknown"),
            "branch_policy_status": report_summary.get("branch_policy_status", "unknown"),
            "publish_status": report_summary.get("publish_status", "unknown"),
            "auth_status": report_summary.get("auth_status", "unknown"),
        }
        return status, summary, metrics
    if key == "ops-status":
        status = _string_or_none(report_summary.get("status")) or "available"
        index_status = report_summary.get("index_status", "unknown")
        latest_bundle_status = report_summary.get("latest_bundle_status", "unknown")
        history_entry_count = report_summary.get("history_entry_count", 0)
        history_limit = report_summary.get("history_limit", 0)
        summary = (
            f"index={index_status} latest_bundle={latest_bundle_status} "
            f"history={history_entry_count}/{history_limit}"
        )
        metrics = {
            "history_entry_count": history_entry_count,
            "history_limit": history_limit,
            "dropped_entry_count": report_summary.get("dropped_entry_count", 0),
            "archive_entry_count": report_summary.get("archive_entry_count", 0),
            "related_report_count": report_summary.get("related_report_count", 0),
        }
        return status, summary, metrics
    if key == "sync-audit":
        status = _string_or_none(report_summary.get("overall_status")) or "available"
        pending = report_summary.get("pending_artifacts", 0)
        integrity = report_summary.get("integrity_issue_count", 0)
        prunable = report_summary.get("prunable_groups", 0)
        summary = f"pending={pending} integrity_issues={integrity} prunable_groups={prunable}"
        metrics = {
            "pending_artifacts": pending,
            "integrity_issue_count": integrity,
            "prunable_groups": prunable,
            "repair_needed_issues": report_summary.get("repair_needed_issues", 0),
            "cleanup_report_mismatches": report_summary.get("cleanup_report_mismatches", 0),
        }
        return status, summary, metrics
    status = _string_or_none(report_summary.get("overall_status")) or "available"
    action_count = report_summary.get("action_count", 0)
    affected = report_summary.get("affected_issue_count", 0)
    summary = f"actions={action_count} affected_issues={affected}"
    metrics = {
        "action_count": action_count,
        "affected_issue_count": affected,
        "sync_applied_action_count": report_summary.get("sync_applied_action_count", 0),
        "replacement_entry_count": report_summary.get("replacement_entry_count", 0),
    }
    return status, summary, metrics


def _report_details(key: str, payload: dict[str, object]) -> dict[str, object]:
    related_reports = payload.get("related_reports")
    related_mismatch_warnings: list[str] = []
    related_mismatch_reports = 0
    related_policy_drift_warnings: list[str] = []
    related_policy_drift_reports = 0
    if key == "sync-health":
        summary = _dict_value(payload, "summary")
        cleanup_group = _sync_health_related_report_group(payload, "cleanup_reports")
        sync_audit_group = _sync_health_related_report_group(payload, "sync_audit_reports")
        cleanup_mismatches = _sync_health_group_warning_lines(cleanup_group, "mismatches")
        cleanup_policy_drifts = _sync_health_group_warning_lines(cleanup_group, "policy_drifts")
        sync_audit_mismatches = _sync_health_group_warning_lines(sync_audit_group, "mismatches")
        sync_audit_policy_drifts = _sync_health_group_warning_lines(sync_audit_group, "policy_drifts")
        related_mismatch_warnings = [*cleanup_mismatches, *sync_audit_mismatches]
        related_policy_drift_warnings = [*cleanup_policy_drifts, *sync_audit_policy_drifts]
        return {
            "related_report_mismatch_warnings": related_mismatch_warnings,
            "related_report_mismatches": summary.get("related_report_mismatches", 0),
            "related_report_policy_drift_warnings": related_policy_drift_warnings,
            "related_report_policy_drifts": summary.get("related_report_policy_drifts", 0),
            "cleanup_related_report_count": cleanup_group.get("total_reports", 0),
            "cleanup_related_report_mismatches": cleanup_group.get("mismatch_reports", 0),
            "cleanup_related_report_policy_drifts": cleanup_group.get("policy_drift_reports", 0),
            "cleanup_related_report_detail_summary": cleanup_group.get("detail_summary"),
            "sync_audit_related_report_count": sync_audit_group.get("total_reports", 0),
            "sync_audit_related_report_mismatches": sync_audit_group.get("mismatch_reports", 0),
            "sync_audit_related_report_policy_drifts": sync_audit_group.get("policy_drift_reports", 0),
            "sync_audit_related_report_detail_summary": sync_audit_group.get("detail_summary"),
            "repair_findings_after": summary.get("repair_findings_after", 0),
            "prunable_groups": summary.get("prunable_groups", 0),
            "repair_needed_issues": summary.get("repair_needed_issues", 0),
            "next_actions": _list_of_strings(summary.get("next_actions")),
        }
    if isinstance(related_reports, dict):
        raw_mismatch_reports = related_reports.get("mismatch_reports")
        if isinstance(raw_mismatch_reports, int):
            related_mismatch_reports = raw_mismatch_reports
        mismatches = related_reports.get("mismatches")
        if isinstance(mismatches, list):
            for entry in mismatches:
                if not isinstance(entry, dict):
                    continue
                label = _string_or_none(entry.get("label")) or "related-report"
                warning = _string_or_none(entry.get("warning")) or "issue filter mismatch"
                related_mismatch_warnings.append(f"{label}: {warning}")
        raw_policy_drift_reports = related_reports.get("policy_drift_reports")
        if isinstance(raw_policy_drift_reports, int):
            related_policy_drift_reports = raw_policy_drift_reports
        policy_drifts = related_reports.get("policy_drifts")
        if isinstance(policy_drifts, list):
            for entry in policy_drifts:
                if not isinstance(entry, dict):
                    continue
                label = _string_or_none(entry.get("label")) or "related-report"
                warning = _string_or_none(entry.get("warning")) or "policy drift"
                related_policy_drift_warnings.append(f"{label}: {warning}")
    if key == "ops-status":
        latest = payload.get("latest")
        if not isinstance(latest, dict):
            latest = {}
        latest_bundle = payload.get("latest_bundle")
        if not isinstance(latest_bundle, dict):
            latest_bundle = {}
        return {
            "latest_entry_id": latest.get("entry_id"),
            "latest_overall_status": latest.get("overall_status"),
            "latest_bundle_status": latest_bundle.get("status"),
            "latest_bundle_component_count": latest_bundle.get("component_count", 0),
            "latest_bundle_cross_link_count": latest_bundle.get("cross_link_count", 0),
            "latest_bundle_path": latest_bundle.get("path"),
            "history_index_path": _dict_value(payload, "index").get("history_json_path"),
            "latest_index_path": _dict_value(payload, "index").get("latest_json_path"),
            "related_report_count": related_reports.get("total", 0)
            if isinstance(related_reports, dict)
            else 0,
        }
    if key == "github-smoke":
        summary = _dict_value(payload, "summary")
        repo_access = _dict_value(payload, "repo_access")
        branch_policy = _dict_value(payload, "branch_policy")
        publish = _dict_value(payload, "publish")
        branch_policy_warnings = branch_policy.get("warnings")
        publish_warnings = publish.get("warnings")
        return {
            "tracker_repo": _dict_value(payload, "meta").get("tracker_repo"),
            "repo_access_message": repo_access.get("message"),
            "full_name": repo_access.get("full_name"),
            "default_branch": repo_access.get("default_branch"),
            "branch_policy_message": branch_policy.get("message"),
            "branch_policy_warning_count": (
                len([item for item in branch_policy_warnings if isinstance(item, str) and item])
                if isinstance(branch_policy_warnings, (list, tuple))
                else 0
            ),
            "publish_message": publish.get("message"),
            "publish_warning_count": (
                len([item for item in publish_warnings if isinstance(item, str) and item])
                if isinstance(publish_warnings, (list, tuple))
                else 0
            ),
            "sampled_issue_id": summary.get("sampled_issue_id"),
        }
    if key == "ops-brief":
        sources = _dict_value(payload, "sources")
        return {
            "top_findings": _list_of_strings(payload.get("top_findings")),
            "next_actions": _list_of_strings(payload.get("next_actions")),
            "doctor_status": _dict_value(sources, "doctor").get("overall_status"),
            "report_health_title": _dict_value(sources, "report_health").get("title"),
            "sync_audit_pending": _dict_value(sources, "sync_audit").get("pending_artifacts", 0),
            "sync_health_integrity_issue_count": _dict_value(sources, "sync_health").get("integrity_issue_count", 0),
            "github_smoke_status": _dict_value(sources, "github_smoke").get("status"),
            "github_smoke_publish_status": _dict_value(sources, "github_smoke").get("publish_status"),
            "github_smoke_branch_policy_status": _dict_value(sources, "github_smoke").get("branch_policy_status"),
        }
    if key != "sync-audit":
        details: dict[str, object] = {}
        if related_mismatch_warnings:
            details["related_report_mismatch_warnings"] = related_mismatch_warnings
            details["related_report_mismatches"] = related_mismatch_reports
        if related_policy_drift_warnings:
            details["related_report_policy_drift_warnings"] = related_policy_drift_warnings
            details["related_report_policy_drifts"] = related_policy_drift_reports
        return details
    integrity = payload.get("integrity")
    if not isinstance(integrity, dict):
        return {}
    finding_counts = integrity.get("finding_counts")
    if not isinstance(finding_counts, dict):
        finding_counts = {}
    reports = integrity.get("reports")
    sample_issue_ids: list[int] = []
    if isinstance(reports, list):
        for report in reports:
            if not isinstance(report, dict):
                continue
            issue_id = report.get("issue_id")
            status = report.get("status")
            if isinstance(issue_id, int) and status == "issues" and issue_id not in sample_issue_ids:
                sample_issue_ids.append(issue_id)
            if len(sample_issue_ids) >= 3:
                break
    return {
        "action_hints": _integrity_action_hints(finding_counts),
        "cleanup_mismatch_warnings": related_mismatch_warnings,
        "cleanup_report_mismatches": related_mismatch_reports,
        "related_report_policy_drift_warnings": related_policy_drift_warnings,
        "related_report_policy_drifts": related_policy_drift_reports,
        "integrity_reports": integrity.get("total_reports", 0),
        "issues_with_findings": integrity.get("issues_with_findings", 0),
        "clean_issues": integrity.get("clean_issues", 0),
        "finding_counts": dict(sorted(finding_counts.items())),
        "sample_issue_ids": sample_issue_ids,
    }


def _extract_report_policy_summary(payload: dict[str, object] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    policy = payload.get("policy")
    if not isinstance(policy, dict):
        return None
    return _string_or_none(policy.get("summary"))


def _extract_report_policy_thresholds(payload: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    policy = payload.get("policy")
    if not isinstance(policy, dict):
        return {}
    thresholds = policy.get("report_freshness_policy")
    if not isinstance(thresholds, dict):
        return {}
    return dict(thresholds)


def _count_report_policy_alignment(entries: list[dict[str, object]]) -> dict[str, int]:
    counts = {"drift": 0, "embedded": 0, "missing": 0}
    for entry in entries:
        alignment_status = _string_or_none(entry.get("policy_alignment_status")) or "missing"
        if alignment_status == "drift":
            counts["drift"] += 1
            counts["embedded"] += 1
        elif alignment_status == "match":
            counts["embedded"] += 1
        else:
            counts["missing"] += 1
    return counts


def _integrity_action_hints(finding_counts: dict[str, object]) -> list[str]:
    ordered: list[tuple[str, int]] = []
    for code, raw_count in finding_counts.items():
        if not isinstance(code, str):
            continue
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = 0
        if count <= 0:
            continue
        ordered.append((code, count))
    ordered.sort(key=lambda item: (-item[1], item[0]))
    hints: list[str] = []
    for code, count in ordered:
        hint = INTEGRITY_FINDING_HINTS.get(code)
        if not hint:
            hint = "review the affected manifest entries and rerun `repoagents sync check` after repair"
        hints.append(f"{code} ({count}): {hint}")
    return hints


def _report_relation_specs(key: str, payload: dict[str, object]) -> list[dict[str, object]]:
    if key == "ops-brief":
        related_reports = payload.get("related_reports")
        if not isinstance(related_reports, dict):
            return []
        entries = related_reports.get("entries")
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, dict)]
    if key == "sync-health":
        related_reports = payload.get("related_reports")
        if not isinstance(related_reports, dict):
            return []
        specs: list[dict[str, object]] = []
        cleanup_group = _sync_health_related_report_group(payload, "cleanup_reports")
        cleanup_labels = _sync_health_group_labels(cleanup_group)
        if cleanup_group and (
            cleanup_group.get("total_reports")
            or cleanup_group.get("mismatch_reports")
            or cleanup_group.get("policy_drift_reports")
        ):
            if int(cleanup_group.get("total_reports", 0) or 0) >= 1 or "Cleanup preview" in cleanup_labels:
                specs.append(
                    _build_sync_health_relation_spec(
                        key="cleanup-preview",
                        label="Cleanup preview",
                        group=cleanup_group,
                    )
                )
            if int(cleanup_group.get("total_reports", 0) or 0) >= 2 or "Cleanup result" in cleanup_labels:
                specs.append(
                    _build_sync_health_relation_spec(
                        key="cleanup-result",
                        label="Cleanup result",
                        group=cleanup_group,
                    )
                )
        sync_audit_group = _sync_health_related_report_group(payload, "sync_audit_reports")
        if sync_audit_group and (
            sync_audit_group.get("total_reports")
            or sync_audit_group.get("mismatch_reports")
            or sync_audit_group.get("policy_drift_reports")
        ):
            specs.append(
                _build_sync_health_relation_spec(
                    key="sync-audit",
                    label="Sync audit",
                    group=sync_audit_group,
                )
            )
        return specs
    related_reports = payload.get("related_reports")
    if not isinstance(related_reports, dict):
        return []
    entries = related_reports.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _sync_health_related_report_group(
    payload: dict[str, object],
    group_key: str,
) -> dict[str, object]:
    related_reports = payload.get("related_reports")
    if not isinstance(related_reports, dict):
        return {}
    group = related_reports.get(group_key)
    if not isinstance(group, dict):
        return {}
    return group


def _sync_health_group_warning_lines(
    group: dict[str, object],
    key: str,
) -> list[str]:
    warnings: list[str] = []
    raw_entries = group.get(key)
    if not isinstance(raw_entries, list):
        return warnings
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        label = _string_or_none(entry.get("label")) or "related-report"
        warning = _string_or_none(entry.get("warning")) or key.rstrip("s")
        warnings.append(f"{label}: {warning}")
    return warnings


def _sync_health_group_labels(group: dict[str, object]) -> set[str]:
    labels: set[str] = set()
    for key in ("mismatches", "policy_drifts"):
        raw_entries = group.get(key)
        if not isinstance(raw_entries, list):
            continue
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            label = _string_or_none(entry.get("label"))
            if label:
                labels.add(label)
    return labels


def _build_sync_health_relation_spec(
    *,
    key: str,
    label: str,
    group: dict[str, object],
) -> dict[str, object]:
    mismatch_reports = int(group.get("mismatch_reports", 0) or 0)
    policy_drift_reports = int(group.get("policy_drift_reports", 0) or 0)
    total_reports = int(group.get("total_reports", 0) or 0)
    warning_parts: list[str] = []
    if mismatch_reports:
        warning_parts.append(f"mismatches={mismatch_reports}")
    if policy_drift_reports:
        warning_parts.append(f"policy_drifts={policy_drift_reports}")
    if not warning_parts and total_reports:
        warning_parts.append(f"related_reports={total_reports}")
    return {
        "key": key,
        "label": label,
        "status": "attention" if warning_parts else "available",
        "warning": ", ".join(warning_parts) if warning_parts else None,
    }


def _attach_report_cross_references(entries: list[dict[str, object]]) -> None:
    by_key = {
        str(entry["key"]): entry
        for entry in entries
        if isinstance(entry.get("key"), str)
    }
    for entry in entries:
        related_cards: list[dict[str, object]] = []
        relation_specs = _list_of_dicts(entry.get("relation_specs"))
        for spec in relation_specs:
            target_key = _string_or_none(spec.get("key"))
            target = by_key.get(target_key) if target_key else None
            related = {
                "key": target_key,
                "label": spec.get("label") or target_key or "related",
                "status": spec.get("status"),
                "card_href": target.get("card_href") if isinstance(target, dict) else None,
                "json_href": target.get("json_href") if isinstance(target, dict) else None,
                "markdown_href": target.get("markdown_href") if isinstance(target, dict) else None,
                "warning": spec.get("warning"),
            }
            policy_alignment = spec.get("policy_alignment")
            if isinstance(policy_alignment, dict):
                related["policy_alignment_status"] = policy_alignment.get("status")
                related["policy_alignment_warning"] = policy_alignment.get("warning")
                related["embedded_policy_summary"] = policy_alignment.get("embedded_summary")
                related["current_policy_summary"] = policy_alignment.get("current_summary")
            related_cards.append(related)
            if isinstance(target, dict):
                referenced_by = target.get("referenced_by")
                if not isinstance(referenced_by, list):
                    referenced_by = []
                    target["referenced_by"] = referenced_by
                referenced_by.append(
                    {
                        "key": entry.get("key"),
                        "label": entry.get("label"),
                        "status": entry.get("status"),
                        "card_href": entry.get("card_href"),
                        "json_href": entry.get("json_href"),
                        "markdown_href": entry.get("markdown_href"),
                    }
                )
        entry["related_cards"] = related_cards


def _serialize_sync_retention_snapshot(
    *,
    loaded: LoadedConfig,
    output_path: Path,
    limit: int,
) -> dict[str, object]:
    snapshot = summarize_sync_applied_retention(
        loaded,
        keep_groups_per_issue=loaded.data.cleanup.sync_applied_keep_groups_per_issue,
        limit=limit,
    )
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
        "entries": [
            _serialize_sync_retention_entry(loaded=loaded, output_path=output_path, entry=entry)
            for entry in snapshot.entries
        ],
    }


def _serialize_sync_retention_entry(
    *,
    loaded: LoadedConfig,
    output_path: Path,
    entry: object,
) -> dict[str, object]:
    if not isinstance(entry, SyncAppliedRetentionIssueSummary):
        raise TypeError("Retention entry must be a SyncAppliedRetentionIssueSummary.")
    return {
        "tracker": entry.tracker,
        "issue_id": entry.issue_id,
        "status": entry.status,
        "keep_groups_limit": entry.keep_groups_limit,
        "integrity_findings": entry.integrity_findings,
        "finding_codes": list(entry.finding_codes),
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
        "issue_root_path": str(entry.issue_root),
        "issue_root_href": _relative_href(output_path, entry.issue_root),
        "manifest_path": str(entry.manifest_path),
        "manifest_href": _relative_href(output_path, entry.manifest_path) if entry.manifest_path.exists() else None,
        "groups": [
            _serialize_sync_retention_group(loaded=loaded, output_path=output_path, group=group)
            for group in entry.groups
        ],
    }


def _serialize_sync_retention_group(
    *,
    loaded: LoadedConfig,
    output_path: Path,
    group: object,
) -> dict[str, object]:
    if not isinstance(group, SyncAppliedRetentionGroup):
        raise TypeError("Retention group must be a SyncAppliedRetentionGroup.")
    archive_links = [
        {
            "path": relative_path,
            "href": _relative_href(output_path, loaded.sync_applied_dir / relative_path),
        }
        for relative_path in group.archive_paths
    ]
    return {
        "group_key": group.group_key,
        "status": group.status,
        "actions": list(group.actions),
        "archive_paths": list(group.archive_paths),
        "archive_links": archive_links,
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


def _serialize_sync_handoff_entry(
    *,
    loaded: LoadedConfig,
    output_path: Path,
    manifest_path: Path,
    entry: dict[str, object],
    source_archive_map: dict[str, str],
) -> dict[str, object]:
    normalized = entry.get("normalized")
    if not isinstance(normalized, dict):
        normalized = {}
    handoff = entry.get("handoff")
    if not isinstance(handoff, dict):
        handoff = {}

    manifest_href = _relative_href(output_path, manifest_path)
    archived_relative_path = _string_or_none(entry.get("archived_relative_path"))
    archived_path = (
        (loaded.sync_applied_dir / archived_relative_path).resolve()
        if archived_relative_path
        else None
    )
    archived_href = _relative_href(output_path, archived_path) if archived_path else None
    source_relative_path = _string_or_none(entry.get("source_relative_path"))
    source_href = _resolve_sync_link_href(
        loaded=loaded,
        output_path=output_path,
        raw_value=source_relative_path,
        source_archive_map=source_archive_map,
    )
    normalized_links = _serialize_normalized_links(
        loaded=loaded,
        output_path=output_path,
        normalized=normalized,
        source_archive_map=source_archive_map,
    )

    search_index = " ".join(
        value.lower()
        for value in (
            _string_or_none(entry.get("summary")) or "",
            _string_or_none(entry.get("action")) or "",
            _string_or_none(entry.get("tracker")) or "",
            _string_or_none(normalized.get("artifact_role")) or "",
            _string_or_none(normalized.get("issue_key")) or "",
            _string_or_none(normalized.get("bundle_key")) or "",
            _string_or_none(source_relative_path) or "",
        )
        if value
    )
    refs = normalized.get("refs")
    if not isinstance(refs, dict):
        refs = {}

    return {
        "tracker": entry.get("tracker"),
        "issue_id": entry.get("issue_id"),
        "action": entry.get("action"),
        "summary": entry.get("summary"),
        "applied_at": entry.get("applied_at"),
        "staged_at": entry.get("staged_at"),
        "entry_key": entry.get("entry_key"),
        "artifact_role": normalized.get("artifact_role"),
        "issue_key": normalized.get("issue_key"),
        "bundle_key": normalized.get("bundle_key"),
        "manifest_path": str(manifest_path),
        "manifest_href": manifest_href,
        "archived_path": str(archived_path) if archived_path else None,
        "archived_href": archived_href,
        "source_relative_path": source_relative_path,
        "source_href": source_href,
        "normalized": normalized,
        "normalized_links": normalized_links,
        "handoff": {
            "group_key": handoff.get("group_key"),
            "group_size": handoff.get("group_size", 0),
            "group_index": handoff.get("group_index", 0),
            "group_actions": handoff.get("group_actions", []),
            "related_entry_keys": handoff.get("related_entry_keys", []),
            "related_source_paths": handoff.get("related_source_paths", []),
        },
        "refs": refs,
        "search_index": search_index,
    }


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


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _report_age_snapshot(*, rendered_at: str, generated_at: str | None) -> tuple[int | None, str, str]:
    rendered_dt = _parse_iso_datetime(rendered_at)
    generated_dt = _parse_iso_datetime(generated_at)
    if rendered_dt is None or generated_dt is None:
        return None, "n/a", "unknown"
    age_seconds = int((rendered_dt - generated_dt).total_seconds())
    if age_seconds < -60:
        return age_seconds, f"in {_format_age_seconds(abs(age_seconds))}", "future"
    normalized_age = max(age_seconds, 0)
    if normalized_age <= 3_600:
        return normalized_age, _format_age_seconds(normalized_age), "fresh"
    if normalized_age <= 86_400:
        return normalized_age, _format_age_seconds(normalized_age), "aging"
    return normalized_age, _format_age_seconds(normalized_age), "stale"


def _serialize_normalized_links(
    *,
    loaded: LoadedConfig,
    output_path: Path,
    normalized: dict[str, object],
    source_archive_map: dict[str, str],
) -> list[dict[str, object]]:
    links = normalized.get("links")
    if not isinstance(links, dict):
        return []
    rendered: list[dict[str, object]] = []
    for label, raw_value in sorted(links.items()):
        target = _string_or_none(raw_value)
        rendered.append(
            {
                "label": label,
                "target": target,
                "href": _resolve_sync_link_href(
                    loaded=loaded,
                    output_path=output_path,
                    raw_value=target,
                    source_archive_map=source_archive_map,
                ),
            }
        )
    return rendered


def _resolve_sync_link_href(
    *,
    loaded: LoadedConfig,
    output_path: Path,
    raw_value: str | None,
    source_archive_map: dict[str, str],
) -> str | None:
    if not raw_value:
        return None
    if raw_value.startswith(("http://", "https://")):
        return raw_value
    resolved_target = _resolve_sync_link_target(
        loaded=loaded,
        raw_value=raw_value,
        source_archive_map=source_archive_map,
    )
    if resolved_target is None:
        return None
    return _relative_href(output_path, resolved_target)


def _resolve_sync_link_target(
    *,
    loaded: LoadedConfig,
    raw_value: str,
    source_archive_map: dict[str, str],
) -> Path | None:
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate

    archived_relative_path = source_archive_map.get(raw_value)
    if archived_relative_path:
        return (loaded.sync_applied_dir / archived_relative_path).resolve()

    sync_applied_candidate = loaded.sync_applied_dir / raw_value
    if sync_applied_candidate.exists():
        return sync_applied_candidate.resolve()

    sync_candidate = loaded.sync_dir / raw_value
    if sync_candidate.exists():
        return sync_candidate.resolve()

    repo_candidate = loaded.repo_root / raw_value
    if repo_candidate.exists():
        return repo_candidate.resolve()
    return None


def _snapshot_section(snapshot: dict[str, object], name: str) -> dict[str, object]:
    section = snapshot[name]
    if not isinstance(section, dict):
        raise TypeError(f"Dashboard snapshot section '{name}' must be a mapping.")
    return section


def _snapshot_mapping(section: dict[str, object], name: str) -> dict[str, object]:
    mapping = section[name]
    if not isinstance(mapping, dict):
        raise TypeError(f"Dashboard snapshot field '{name}' must be a mapping.")
    return mapping


def _snapshot_runs(snapshot: dict[str, object]) -> list[dict[str, object]]:
    runs = snapshot["runs"]
    if not isinstance(runs, list):
        raise TypeError("Dashboard snapshot field 'runs' must be a list.")
    return _list_of_dicts(runs)


def _snapshot_sync_handoffs(snapshot: dict[str, object]) -> list[dict[str, object]]:
    sync_handoffs = snapshot["sync_handoffs"]
    if not isinstance(sync_handoffs, list):
        raise TypeError("Dashboard snapshot field 'sync_handoffs' must be a list.")
    return _list_of_dicts(sync_handoffs)


def _snapshot_sync_retention(snapshot: dict[str, object]) -> dict[str, object]:
    sync_retention = snapshot["sync_retention"]
    if not isinstance(sync_retention, dict):
        raise TypeError("Dashboard snapshot field 'sync_retention' must be a mapping.")
    return sync_retention


def _snapshot_ops_snapshots(snapshot: dict[str, object]) -> dict[str, object]:
    ops_snapshots = snapshot["ops_snapshots"]
    if not isinstance(ops_snapshots, dict):
        raise TypeError("Dashboard snapshot field 'ops_snapshots' must be a mapping.")
    return ops_snapshots


def _snapshot_reports(snapshot: dict[str, object]) -> dict[str, object]:
    reports = snapshot["reports"]
    if not isinstance(reports, dict):
        raise TypeError("Dashboard snapshot field 'reports' must be a mapping.")
    return reports


def _build_report_freshness_policy_snapshot(loaded: LoadedConfig) -> dict[str, object]:
    policy = loaded.data.dashboard.report_freshness_policy
    return {
        "summary": _format_report_freshness_policy_summary(
            unknown_issues_threshold=policy.unknown_issues_threshold,
            stale_issues_threshold=policy.stale_issues_threshold,
            future_attention_threshold=policy.future_attention_threshold,
            aging_attention_threshold=policy.aging_attention_threshold,
        ),
        "report_freshness_policy": {
            "unknown_issues_threshold": policy.unknown_issues_threshold,
            "stale_issues_threshold": policy.stale_issues_threshold,
            "future_attention_threshold": policy.future_attention_threshold,
            "aging_attention_threshold": policy.aging_attention_threshold,
        },
    }


def _combine_severities(values: list[str]) -> str:
    winner = "clean"
    winner_rank = SEVERITY_ORDER[winner]
    for value in values:
        rank = SEVERITY_ORDER.get(value, SEVERITY_ORDER["attention"])
        if rank > winner_rank:
            winner = value
            winner_rank = rank
    return winner


def _count_report_freshness(
    entries: list[dict[str, object]],
    *,
    key_prefix: str | None = None,
) -> dict[str, int]:
    counts = {
        "fresh": 0,
        "aging": 0,
        "stale": 0,
        "future": 0,
        "unknown": 0,
    }
    for entry in entries:
        key = _string_or_none(entry.get("key"))
        if not key:
            continue
        if key_prefix and not key.startswith(key_prefix):
            continue
        freshness = _string_or_none(entry.get("freshness_status")) or "unknown"
        if freshness not in counts:
            freshness = "unknown"
        counts[freshness] += 1
    return counts


def _report_freshness_severity(
    value: dict[str, object],
    *,
    unknown_issues_threshold: int,
    stale_issues_threshold: int,
    future_attention_threshold: int,
    aging_attention_threshold: int,
) -> tuple[str, str]:
    unknown = int(value.get("unknown", 0) or 0)
    stale = int(value.get("stale", 0) or 0)
    future = int(value.get("future", 0) or 0)
    aging = int(value.get("aging", 0) or 0)
    total = sum(int(item or 0) for item in value.values())
    if unknown >= unknown_issues_threshold:
        return "issues", "unknown freshness reports need metadata or parsing repair"
    if stale >= stale_issues_threshold:
        return "issues", "stale reports need regeneration or operator review"
    if unknown > 0:
        return "attention", "unknown freshness reports should be inspected for metadata gaps"
    if stale > 0:
        return "attention", "stale reports are below the issue threshold but should be refreshed"
    if future >= future_attention_threshold:
        return "attention", "future-dated reports may indicate clock skew or staged exports"
    if aging >= aging_attention_threshold:
        return "attention", "aging reports should be refreshed soon"
    if total == 0:
        return "clean", "no reports exported yet"
    return "clean", "all report freshness snapshots are current"


def _report_policy_drift_severity(policy_drift_total: int) -> tuple[str, str]:
    if policy_drift_total > 0:
        return (
            "attention",
            f"embedded policy drift was detected in raw report exports; {_report_policy_drift_guidance_summary()}",
        )
    return "clean", "embedded policy metadata matches current config or is absent"


def _combine_report_summary_severity(
    *,
    freshness_severity: str,
    freshness_reason: str,
    policy_drift_severity: str,
    policy_drift_reason: str,
) -> tuple[str, str]:
    severity = _combine_severities([freshness_severity, policy_drift_severity])
    if policy_drift_severity == "clean":
        return freshness_severity, freshness_reason
    if freshness_severity == "clean":
        return policy_drift_severity, policy_drift_reason
    return severity, f"{freshness_reason}; {policy_drift_reason}"


def _build_hero_snapshot(
    reports: dict[str, object],
    *,
    include_policy_drift: bool = False,
) -> dict[str, object]:
    if include_policy_drift:
        report_severity = _string_or_none(reports.get("report_summary_severity")) or "clean"
        report_reason = (
            _string_or_none(reports.get("report_summary_severity_reason")) or "n/a"
        )
    else:
        report_severity = _string_or_none(reports.get("freshness_severity")) or "clean"
        report_reason = _string_or_none(reports.get("freshness_severity_reason")) or "n/a"
    freshness_severity = _string_or_none(reports.get("freshness_severity")) or "clean"
    cleanup_severity = _string_or_none(reports.get("cleanup_freshness_severity")) or "clean"
    cleanup_reason = _string_or_none(reports.get("cleanup_freshness_severity_reason")) or "n/a"
    cleanup_total = int(reports.get("cleanup_total", 0) or 0)
    policy_drift_total = int(reports.get("policy_drift_total", 0) or 0)
    policy_drift_severity = _string_or_none(reports.get("policy_drift_severity")) or "clean"
    chips = [
        {
            "label": "Report freshness",
            "severity": report_severity,
            "value": _format_report_freshness_summary(_snapshot_mapping(reports, "freshness")),
        }
    ]
    if include_policy_drift and policy_drift_total > 0:
        drift_value = "1 report" if policy_drift_total == 1 else f"{policy_drift_total} reports"
        chips.append(
            {
                "label": "Policy drift",
                "severity": policy_drift_severity,
                "value": drift_value,
            }
        )
    severities = [report_severity]
    if cleanup_total > 0:
        chips.append(
            {
                "label": "Cleanup freshness",
                "severity": cleanup_severity,
                "value": _format_report_freshness_summary(
                    _snapshot_mapping(reports, "cleanup_freshness")
                ),
            }
        )
        severities.append(cleanup_severity)
    severity = _combine_severities(severities)
    drift_only_attention = (
        include_policy_drift
        and policy_drift_total > 0
        and report_severity == "attention"
        and freshness_severity == "clean"
        and cleanup_severity == "clean"
    )
    if severity == "issues":
        title = "Report freshness needs action"
    elif drift_only_attention:
        title = "Report policy drift needs follow-up"
    elif severity == "attention":
        title = "Report freshness needs follow-up"
    else:
        title = "Report freshness is clean"
    summary_parts = [f"Overall reports are {report_severity}: {report_reason}."]
    if cleanup_total > 0:
        summary_parts.append(f"Cleanup reports are {cleanup_severity}: {cleanup_reason}.")
    return {
        "severity": severity,
        "title": title,
        "summary": " ".join(summary_parts),
        "reporting_chips": chips,
    }


def _render_report_metrics(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    return ", ".join(
        f"{key}={item}"
        for key, item in sorted(value.items())
        if item not in (None, "", [])
    ) or "none"


def _format_report_freshness_summary(value: dict[str, object]) -> str:
    fresh = int(value.get("fresh", 0) or 0)
    aging = int(value.get("aging", 0) or 0)
    stale = int(value.get("stale", 0) or 0)
    future = int(value.get("future", 0) or 0)
    unknown = int(value.get("unknown", 0) or 0)
    total = fresh + aging + stale + future + unknown
    if total == 0:
        return "none"
    segments = [
        f"fresh {fresh}",
        f"aging {aging}",
        f"stale {stale}",
    ]
    if future:
        segments.append(f"future {future}")
    if unknown:
        segments.append(f"unknown {unknown}")
    return " · ".join(segments) + f" / {total} total"


def _format_report_freshness_policy_summary(
    *,
    unknown_issues_threshold: int,
    stale_issues_threshold: int,
    future_attention_threshold: int,
    aging_attention_threshold: int,
) -> str:
    return (
        f"unknown>={unknown_issues_threshold} "
        f"stale>={stale_issues_threshold} "
        f"future>={future_attention_threshold} "
        f"aging>={aging_attention_threshold}"
    )


def _report_policy_drift_guidance_summary() -> str:
    return build_report_policy_drift_guidance()["summary"]


def _report_policy_drift_guidance_detail() -> str:
    return build_report_policy_drift_guidance()["detail"]


def _render_report_details(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    rendered: list[str] = []
    for key, item in sorted(value.items()):
        if item in (None, "", [], {}):
            continue
        if isinstance(item, dict):
            nested = ", ".join(
                f"{nested_key}={nested_value}"
                for nested_key, nested_value in sorted(item.items())
            )
            rendered.append(f"{key}=[{nested}]")
            continue
        if isinstance(item, list):
            rendered.append(f"{key}={','.join(str(entry) for entry in item)}")
            continue
        rendered.append(f"{key}={item}")
    return ", ".join(rendered) or "none"


def _render_report_detail_items(details: dict[str, object]) -> list[str]:
    items: list[str] = []
    for key, value in sorted(details.items()):
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict):
            rendered = ", ".join(
                f"{nested_key}={nested_value}"
                for nested_key, nested_value in sorted(value.items())
            )
            items.append(f"<li><strong>{escape(str(key))}:</strong> {escape(rendered or 'none')}</li>")
            continue
        if isinstance(value, list):
            rendered = ", ".join(str(entry) for entry in value) or "none"
            items.append(f"<li><strong>{escape(str(key))}:</strong> {escape(rendered)}</li>")
            continue
        items.append(f"<li><strong>{escape(str(key))}:</strong> {escape(str(value))}</li>")
    return items


def _render_report_relations(value: object) -> str:
    entries = _list_of_dicts(value)
    if not entries:
        return "none"
    labels = [
        str(entry["label"])
        for entry in entries
        if entry.get("label")
    ]
    return ", ".join(labels) if labels else "none"


def _render_related_report_detail_lines(
    details_value: object,
    *,
    remediation: str | None,
) -> list[str]:
    if not isinstance(details_value, dict):
        return []
    mismatch_warnings = _related_report_warning_list(details_value, kind="mismatch")
    policy_drift_warnings = _related_report_warning_list(details_value, kind="policy_drift")
    block = build_related_report_detail_block(
        mismatch_warnings=mismatch_warnings,
        policy_drift_warnings=policy_drift_warnings,
        remediation=remediation,
    )
    return list(
        render_related_report_detail_lines(
            block,
            title=f"{format_related_report_detail_title('machine')}:",
            section_label_style="machine",
            remediation_label_style="machine",
            layout_policy=build_related_report_detail_line_layout("machine_markdown"),
        )
    )


def _build_related_report_detail_summary(
    details_value: object,
    *,
    remediation: str | None,
) -> str | None:
    if not isinstance(details_value, dict):
        return None
    mismatch_warnings = _related_report_warning_list(details_value, kind="mismatch")
    policy_drift_warnings = _related_report_warning_list(details_value, kind="policy_drift")
    return build_related_report_detail_summary(
        mismatch_warnings=mismatch_warnings,
        policy_drift_warnings=policy_drift_warnings,
        remediation=remediation,
    )


def _render_related_report_detail_html(details_value: object) -> str:
    if not isinstance(details_value, dict):
        return ""
    mismatch_warnings = _related_report_warning_list(details_value, kind="mismatch")
    policy_drift_warnings = _related_report_warning_list(details_value, kind="policy_drift")
    block = build_related_report_detail_block(
        mismatch_warnings=mismatch_warnings,
        policy_drift_warnings=policy_drift_warnings,
        remediation=_report_policy_drift_guidance_detail(),
    )
    return "".join(
        render_related_report_detail_html_fragments(
            block,
            title_style="display",
            section_label_style="display",
            remediation_label_style="display",
            layout_policy=build_related_report_detail_html_layout(),
        )
    )


def _related_report_warning_list(details_value: dict[str, object], *, kind: str) -> list[str]:
    if kind == "mismatch":
        warnings = collect_related_report_warning_lines(
            details_value.get("cleanup_mismatch_warnings"),
            details_value.get("related_report_mismatch_warnings"),
        )
    else:
        warnings = collect_related_report_warning_lines(
            details_value.get("related_report_policy_drift_warnings"),
        )
    return list(warnings)


def _list_of_dicts(items: object) -> list[dict[str, object]]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _list_of_strings(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, str) and item]


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
