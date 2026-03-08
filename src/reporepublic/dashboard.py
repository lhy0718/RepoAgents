from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import quote

from reporepublic.config import LoadedConfig
from reporepublic.models import RunRecord
from reporepublic.models.domain import utc_now
from reporepublic.orchestrator import RunStateStore
from reporepublic.utils.files import write_text_file


@dataclass(frozen=True, slots=True)
class DashboardBuildResult:
    output_path: Path
    total_runs: int
    visible_runs: int
    exported_paths: dict[str, Path]


VALID_DASHBOARD_FORMATS = ("html", "json", "markdown")


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
    log_file = loaded.logs_dir / "reporepublic.jsonl"
    snapshot_runs = [
        _serialize_run_record(loaded, record, output_path) for record in visible_records
    ]
    sync_handoffs = _load_sync_handoffs(
        loaded=loaded,
        output_path=output_path,
        limit=sync_limit,
    )
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
            "logs_path": str(log_file) if log_file.exists() else None,
        },
        "counts": {
            "total_runs": len(all_records),
            "visible_runs": len(visible_records),
            "total_sync_handoffs": sync_handoffs["total"],
            "visible_sync_handoffs": len(sync_handoffs["entries"]),
            "by_status": dict(sorted(counts.items())),
        },
        "runs": snapshot_runs,
        "sync_handoffs": sync_handoffs["entries"],
    }


def render_dashboard_html(*, snapshot: dict[str, object]) -> str:
    meta = _snapshot_section(snapshot, "meta")
    runtime = _snapshot_section(snapshot, "runtime")
    counts = _snapshot_section(snapshot, "counts")
    runs = _snapshot_runs(snapshot)
    sync_handoffs = _snapshot_sync_handoffs(snapshot)
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
    ]
    logs_path = runtime.get("logs_path")
    if isinstance(logs_path, str) and logs_path:
        runtime_links.append(
            _render_link_chip(
                "logs",
                _relative_href(output_path, Path(logs_path)),
            )
        )

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

    runs_markup = "\n".join(_render_run_card(run) for run in runs)
    if not runs_markup:
        runs_markup = """
        <article class="empty-state">
          <h2>No runs recorded yet</h2>
          <p>Run <code>republic run --once</code>, <code>republic trigger &lt;issue-id&gt;</code>, or a webhook-triggered execution to populate the dashboard.</p>
        </article>
        """
    handoff_markup = "\n".join(_render_sync_handoff_card(handoff) for handoff in sync_handoffs)
    if not handoff_markup:
        handoff_markup = """
        <article class="empty-state">
          <h2>No sync handoffs archived yet</h2>
          <p>Apply staged tracker handoffs with <code>republic sync apply</code> to populate this section.</p>
        </article>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>RepoRepublic Operations Dashboard</title>
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
      .runs,
      .handoffs {{
        display: grid;
        gap: 1rem;
      }}
      .run-card,
      .handoff-card {{
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
      <section class="hero" data-default-refresh-seconds="{refresh_seconds}">
        <p class="eyebrow">RepoRepublic operations dashboard</p>
        <h1>Repository runs at a glance</h1>
        <p class="subtitle">This view is generated from local RepoRepublic state. It highlights the latest runs, persisted artifacts, retry posture, and failure reasons without needing a separate service.</p>
        <div class="meta-row">
          <span class="meta-chip">rendered_at {escape(rendered_at)}</span>
          <span class="meta-chip">repo {escape(repo_name)}</span>
          <span class="meta-chip">last_updated {escape(last_updated)}</span>
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
    runs = _snapshot_runs(snapshot)
    sync_handoffs = _snapshot_sync_handoffs(snapshot)
    status_counts = _snapshot_mapping(counts, "by_status")
    lines = [
        "# RepoRepublic Dashboard Snapshot",
        "",
        f"- rendered_at: {meta['rendered_at']}",
        f"- repo: {meta['repo_name']}",
        f"- total_runs: {counts['total_runs']}",
        f"- visible_runs: {counts['visible_runs']}",
        f"- total_sync_handoffs: {counts['total_sync_handoffs']}",
        f"- visible_sync_handoffs: {counts['visible_sync_handoffs']}",
        "",
        "## Status counts",
    ]
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
        return "\n".join(lines) + "\n"

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
    return "\n".join(lines) + "\n"


def _render_metric_card(label: str, value: str) -> str:
    metric_id = "visible-runs-count" if label == "Visible runs" else ""
    id_attr = f' id="{metric_id}"' if metric_id else ""
    return (
        '<article class="metric-card">'
        f'<span class="metric-label">{escape(label)}</span>'
        f'<span class="metric-value"{id_attr}>{escape(value)}</span>'
        "</article>"
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


def _list_of_dicts(items: object) -> list[dict[str, object]]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
