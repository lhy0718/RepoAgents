from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from repoagents.config import LoadedConfig
from repoagents.models.domain import utc_now
from repoagents.utils.files import write_text_file


VALID_OPS_STATUS_FORMATS = ("json", "markdown")


@dataclass(frozen=True, slots=True)
class OpsStatusBuildResult:
    output_paths: dict[str, Path]
    snapshot: dict[str, Any]


def normalize_ops_status_formats(
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
            for item in VALID_OPS_STATUS_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_OPS_STATUS_FORMATS:
            raise ValueError(
                "Unsupported ops status format. Expected one of: json, markdown, all"
            )
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def resolve_ops_status_export_paths(
    target: Path,
    formats: tuple[str, ...],
) -> dict[str, Path]:
    resolved = target.resolve()
    export_paths: dict[str, Path] = {}
    for export_format in formats:
        suffix = ".md" if export_format == "markdown" else ".json"
        export_paths[export_format] = resolved.with_suffix(suffix)
    return export_paths


def build_ops_status_snapshot(
    *,
    loaded: LoadedConfig,
    history_preview_limit: int = 10,
) -> dict[str, Any]:
    rendered_at = utc_now().isoformat()
    ops_root = loaded.reports_dir / "ops"
    latest_json = ops_root / "latest.json"
    latest_markdown = ops_root / "latest.md"
    history_json = ops_root / "history.json"
    history_markdown = ops_root / "history.md"

    latest_load = _load_json_file(latest_json)
    history_load = _load_json_file(history_json)
    index_status = _combine_index_status(latest_load["status"], history_load["status"])

    latest_payload = latest_load["payload"]
    history_payload = history_load["payload"]
    latest_entry_raw = _mapping(latest_payload, "latest")
    history_meta = _mapping(history_payload, "meta")
    raw_history_entries = [
        entry
        for entry in _list(history_payload.get("entries"))
        if isinstance(entry, dict)
    ]

    latest_entry = (
        _serialize_index_entry(latest_entry_raw, rendered_at=rendered_at)
        if latest_entry_raw
        else {}
    )
    history_entries = [
        _serialize_index_entry(entry, rendered_at=rendered_at)
        for entry in raw_history_entries[: max(1, history_preview_limit)]
    ]
    if not history_entries and latest_entry:
        history_entries = [latest_entry]

    latest_bundle = _load_latest_bundle_snapshot(
        latest_entry_raw=latest_entry_raw,
        rendered_at=rendered_at,
    )
    history_entry_count = int(
        history_meta.get(
            "entry_count",
            len(raw_history_entries) or (1 if latest_entry else 0),
        )
        or 0
    )
    history_limit = int(history_meta.get("history_limit", 0) or 0)
    dropped_entry_count = int(history_meta.get("dropped_entry_count", 0) or 0)
    archive_entry_count = sum(1 for entry in raw_history_entries if _entry_has_archive(entry))
    if not raw_history_entries and latest_entry_raw and _entry_has_archive(latest_entry_raw):
        archive_entry_count = 1

    summary = _build_ops_status_summary(
        index_status=index_status,
        latest_entry=latest_entry,
        latest_bundle=latest_bundle,
        history_entry_count=history_entry_count,
        history_limit=history_limit,
        dropped_entry_count=dropped_entry_count,
        archive_entry_count=archive_entry_count,
        history_preview_count=len(history_entries),
    )
    policy = _build_policy_snapshot(loaded)
    related_reports = _build_related_report_snapshot(latest_bundle)
    summary["related_report_count"] = related_reports["total"]
    return {
        "meta": {
            "kind": "ops_status",
            "rendered_at": rendered_at,
            "repo_root": str(loaded.repo_root),
            "ops_root": str(ops_root),
            "history_preview_limit": max(1, history_preview_limit),
        },
        "summary": summary,
        "policy": policy,
        "index": {
            "status": index_status,
            "latest_json_path": str(latest_json) if latest_json.exists() else None,
            "latest_markdown_path": str(latest_markdown) if latest_markdown.exists() else None,
            "history_json_path": str(history_json) if history_json.exists() else None,
            "history_markdown_path": str(history_markdown) if history_markdown.exists() else None,
        },
        "latest": latest_entry,
        "history": history_entries,
        "latest_bundle": latest_bundle,
        "related_reports": related_reports,
    }


def build_ops_status_exports(
    *,
    snapshot: dict[str, Any],
    output_path: Path,
    formats: tuple[str, ...],
) -> OpsStatusBuildResult:
    export_paths = resolve_ops_status_export_paths(output_path, formats)
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_ops_status_json(snapshot))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_ops_status_markdown(snapshot))
    return OpsStatusBuildResult(output_paths=export_paths, snapshot=snapshot)


def render_ops_status_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True)


def render_ops_status_markdown(snapshot: dict[str, Any]) -> str:
    meta = _mapping(snapshot, "meta")
    summary = _mapping(snapshot, "summary")
    policy = _mapping(snapshot, "policy")
    index = _mapping(snapshot, "index")
    latest = _mapping(snapshot, "latest")
    history = _list(snapshot.get("history"))
    latest_bundle = _mapping(snapshot, "latest_bundle")
    related_reports = _mapping(snapshot, "related_reports")

    lines = [
        "# Ops snapshot status",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- ops_root: {meta.get('ops_root', '-')}",
        f"- history_preview_limit: {meta.get('history_preview_limit', 0)}",
        "",
        "## Summary",
        f"- status: {summary.get('status', '-')}",
        f"- message: {summary.get('message', '-')}",
        f"- index_status: {summary.get('index_status', '-')}",
        f"- latest_bundle_status: {summary.get('latest_bundle_status', '-')}",
        f"- history_entry_count: {summary.get('history_entry_count', 0)}",
        f"- history_limit: {summary.get('history_limit', 0)}",
        f"- history_preview_count: {summary.get('history_preview_count', 0)}",
        f"- dropped_entry_count: {summary.get('dropped_entry_count', 0)}",
        f"- archive_entry_count: {summary.get('archive_entry_count', 0)}",
        f"- latest_entry_id: {summary.get('latest_entry_id', '-')}",
        f"- latest_overall_status: {summary.get('latest_overall_status', '-')}",
        f"- related_report_count: {summary.get('related_report_count', 0)}",
        "",
        "## Policy",
        f"- summary: {policy.get('summary', '-')}",
        f"- thresholds: {_format_scalar(_mapping(policy, 'report_freshness_policy'))}",
        "",
        "## Index files",
        f"- latest_json_path: {index.get('latest_json_path', '-')}",
        f"- latest_markdown_path: {index.get('latest_markdown_path', '-')}",
        f"- history_json_path: {index.get('history_json_path', '-')}",
        f"- history_markdown_path: {index.get('history_markdown_path', '-')}",
    ]

    lines.extend(["", "## Latest entry"])
    if latest:
        lines.extend(_render_index_entry_markdown(latest))
    else:
        lines.append("- none")

    lines.extend(["", "## Latest bundle manifest"])
    lines.extend(
        [
            f"- status: {latest_bundle.get('status', '-')}",
            f"- path: {latest_bundle.get('path', '-')}",
            f"- markdown_path: {latest_bundle.get('markdown_path', '-')}",
            f"- landing_html_path: {latest_bundle.get('landing_html_path', '-')}",
            f"- landing_markdown_path: {latest_bundle.get('landing_markdown_path', '-')}",
            f"- brief_json_path: {latest_bundle.get('brief_json_path', '-')}",
            f"- brief_markdown_path: {latest_bundle.get('brief_markdown_path', '-')}",
            f"- overall_status: {latest_bundle.get('overall_status', '-')}",
            f"- component_count: {latest_bundle.get('component_count', 0)}",
            f"- cross_link_count: {latest_bundle.get('cross_link_count', 0)}",
        ]
    )
    if latest_bundle.get("error"):
        lines.append(f"- error: {latest_bundle['error']}")
    component_statuses = _mapping(latest_bundle, "component_statuses")
    if component_statuses:
        lines.append("- component_statuses:")
        lines.extend(f"  - {name}: {status}" for name, status in component_statuses.items())
    components = [
        component
        for component in _list(latest_bundle.get("components"))
        if isinstance(component, dict)
    ]
    if components:
        for component in components:
            lines.extend(
                [
                    "",
                    f"### {component.get('key', 'unknown')}",
                    f"- status: {component.get('status', '-')}",
                    f"- summary: {component.get('summary', '-')}",
                ]
            )
            if component.get("reason"):
                lines.append(f"- reason: {component['reason']}")
            metrics = _mapping(component, "metrics")
            if metrics:
                lines.append("- metrics:")
                lines.extend(f"  - {key}: {_format_scalar(value)}" for key, value in metrics.items())
            output_paths = _mapping(component, "output_paths")
            if output_paths:
                lines.append("- output_paths:")
                lines.extend(f"  - {key}: {value}" for key, value in output_paths.items())
    cross_links = [
        entry for entry in _list(latest_bundle.get("cross_links")) if isinstance(entry, dict)
    ]
    if cross_links:
        lines.extend(["", "## Bundle cross links"])
        for entry in cross_links:
            lines.extend(
                [
                    f"- {entry.get('source', '-')} -> {entry.get('target', '-')}",
                    f"  - status: {entry.get('status', '-')}",
                    f"  - reason: {entry.get('reason', '-')}",
                ]
            )

    lines.extend(["", "## Related reports"])
    related_entries = [
        entry
        for entry in _list(related_reports.get("entries"))
        if isinstance(entry, dict)
    ]
    if not related_entries:
        lines.append("- none")
    else:
        for entry in related_entries:
            lines.extend(
                [
                    f"- {entry.get('label', entry.get('key', 'related'))}",
                    f"  - key: {entry.get('key', '-')}",
                    f"  - status: {entry.get('status', '-')}",
                    f"  - warning: {entry.get('warning', '-')}",
                ]
            )

    lines.extend(["", "## History preview"])
    if not history:
        lines.append("- none")
    else:
        for entry in history:
            if not isinstance(entry, dict):
                continue
            lines.extend(["", * _render_index_entry_markdown(entry)])
    return "\n".join(lines) + "\n"


def render_ops_status_text(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot, "summary")
    latest = _mapping(snapshot, "latest")
    latest_bundle = _mapping(snapshot, "latest_bundle")
    history = [
        entry for entry in _list(snapshot.get("history")) if isinstance(entry, dict)
    ]

    lines = [
        "Ops snapshot status: "
        f"status={summary.get('status', 'unknown')} "
        f"index={summary.get('index_status', 'unknown')} "
        f"entries={summary.get('history_entry_count', 0)}/"
        f"{summary.get('history_limit', 0)} "
        f"archives={summary.get('archive_entry_count', 0)} "
        f"dropped={summary.get('dropped_entry_count', 0)}",
        f"Message: {summary.get('message', 'n/a')}",
    ]
    if latest:
        lines.append(
            "Latest index entry: "
            f"{latest.get('entry_id', 'n/a')} "
            f"overall={latest.get('overall_status', 'unknown')} "
            f"brief={latest.get('brief_severity', 'unknown')} "
            f"age={latest.get('age_human', 'n/a')}"
        )
        lines.append(f"  bundle: {latest.get('bundle_dir', 'n/a')}")
        lines.append(f"  brief: {latest.get('brief_headline', 'n/a')}")
        if latest.get("landing_html"):
            lines.append(f"  landing html: {latest['landing_html']}")
        if latest.get("brief_json"):
            lines.append(f"  brief json: {latest['brief_json']}")
        if latest.get("archive_path"):
            lines.append(f"  archive: {latest['archive_path']}")
    else:
        lines.append("Latest index entry: none")

    lines.append(
        "Latest bundle manifest: "
        f"status={latest_bundle.get('status', 'unknown')} "
        f"overall={latest_bundle.get('overall_status', 'n/a')} "
        f"components={latest_bundle.get('component_count', 0)} "
        f"cross_links={latest_bundle.get('cross_link_count', 0)}"
    )
    if latest_bundle.get("path"):
        lines.append(f"  manifest: {latest_bundle['path']}")
    if latest_bundle.get("error"):
        lines.append(f"  error: {latest_bundle['error']}")
    for component in _list(latest_bundle.get("components")):
        if not isinstance(component, dict):
            continue
        lines.append(
            f"  - {component.get('key', 'unknown')}: "
            f"{component.get('status', 'unknown')} | {component.get('summary', '-')}"
        )
    if history:
        lines.append("History preview:")
        for entry in history:
            lines.append(
                "  - "
                f"{entry.get('entry_id', 'n/a')} | "
                f"{entry.get('overall_status', 'unknown')} | "
                f"brief={entry.get('brief_severity', 'unknown')} | "
                f"age={entry.get('age_human', 'n/a')} | "
                f"archive={'yes' if entry.get('has_archive') else 'no'}"
            )
    else:
        lines.append("History preview: none")
    return "\n".join(lines) + "\n"


def _build_ops_status_summary(
    *,
    index_status: str,
    latest_entry: dict[str, Any],
    latest_bundle: dict[str, Any],
    history_entry_count: int,
    history_limit: int,
    dropped_entry_count: int,
    archive_entry_count: int,
    history_preview_count: int,
) -> dict[str, Any]:
    latest_bundle_status = _string_or_none(latest_bundle.get("status")) or "not_applicable"
    latest_overall_status = _string_or_none(latest_entry.get("overall_status")) or "missing"
    status = "clean"
    if index_status == "missing":
        status = "missing"
        message = "No ops snapshot index has been recorded yet."
    elif index_status == "invalid":
        status = "issues"
        message = "Ops snapshot index files are present but unreadable."
    elif latest_bundle_status in {"missing", "invalid"}:
        status = "issues"
        message = "Latest ops snapshot entry points to a missing or unreadable bundle manifest."
    elif index_status == "partial":
        status = "attention"
        message = "Ops snapshot index is only partially available; latest bundle data was recovered where possible."
    elif latest_overall_status == "issues":
        status = "issues"
        message = "Latest ops snapshot bundle reports issues."
    elif latest_overall_status == "attention":
        status = "attention"
        message = "Latest ops snapshot bundle needs operator follow-up."
    else:
        message = "Latest ops snapshot bundle is available."
    return {
        "status": status,
        "message": message,
        "index_status": index_status,
        "latest_bundle_status": latest_bundle_status,
        "history_entry_count": history_entry_count,
        "history_limit": history_limit,
        "history_preview_count": history_preview_count,
        "dropped_entry_count": dropped_entry_count,
        "archive_entry_count": archive_entry_count,
        "latest_entry_id": latest_entry.get("entry_id"),
        "latest_overall_status": latest_entry.get("overall_status"),
    }


def _build_policy_snapshot(loaded: LoadedConfig) -> dict[str, Any]:
    policy = loaded.data.dashboard.report_freshness_policy
    thresholds = {
        "unknown_issues_threshold": policy.unknown_issues_threshold,
        "stale_issues_threshold": policy.stale_issues_threshold,
        "future_attention_threshold": policy.future_attention_threshold,
        "aging_attention_threshold": policy.aging_attention_threshold,
    }
    return {
        "summary": (
            f"unknown>={policy.unknown_issues_threshold} "
            f"stale>={policy.stale_issues_threshold} "
            f"future>={policy.future_attention_threshold} "
            f"aging>={policy.aging_attention_threshold}"
        ),
        "report_freshness_policy": thresholds,
    }


def _build_related_report_snapshot(latest_bundle: dict[str, Any]) -> dict[str, Any]:
    relation_map = {
        "ops_brief": ("ops-brief", "Ops brief"),
        "github_smoke": ("github-smoke", "GitHub smoke"),
        "sync_audit": ("sync-audit", "Sync audit"),
        "sync_health": ("sync-health", "Sync health"),
        "cleanup_preview": ("cleanup-preview", "Cleanup preview"),
        "cleanup_result": ("cleanup-result", "Cleanup result"),
    }
    entries: list[dict[str, Any]] = []
    for component in _list(latest_bundle.get("components")):
        if not isinstance(component, dict):
            continue
        key = _string_or_none(component.get("key"))
        mapped = relation_map.get(key) if key else None
        if mapped is None:
            continue
        report_key, label = mapped
        status = _string_or_none(component.get("status")) or "unknown"
        warning = None
        if status in {"attention", "issues"}:
            warning = f"latest bundle component status is {status}"
        entries.append(
            {
                "key": report_key,
                "label": label,
                "status": status,
                "warning": warning,
            }
        )
    return {
        "total": len(entries),
        "entries": entries,
    }


def _load_latest_bundle_snapshot(
    *,
    latest_entry_raw: dict[str, Any],
    rendered_at: str,
) -> dict[str, Any]:
    if not latest_entry_raw:
        return {
            "status": "not_applicable",
            "path": None,
            "markdown_path": None,
            "landing_html_path": None,
            "landing_markdown_path": None,
            "brief_json_path": None,
            "brief_markdown_path": None,
            "overall_status": None,
            "component_count": 0,
            "cross_link_count": 0,
            "component_statuses": {},
            "components": [],
            "cross_links": [],
            "error": None,
            "age_seconds": None,
            "age_human": "n/a",
        }

    bundle_json_path = _coerce_path(latest_entry_raw.get("bundle_json"))
    bundle_dir = _coerce_path(latest_entry_raw.get("bundle_dir"))
    if bundle_json_path is None and bundle_dir is not None:
        bundle_json_path = bundle_dir / "bundle.json"
    bundle_markdown_path = _coerce_path(latest_entry_raw.get("bundle_markdown"))
    if bundle_markdown_path is None and bundle_dir is not None:
        bundle_markdown_path = bundle_dir / "bundle.md"
    landing_html_path = _coerce_path(latest_entry_raw.get("landing_html"))
    if landing_html_path is None and bundle_dir is not None:
        landing_html_path = bundle_dir / "index.html"
    landing_markdown_path = _coerce_path(latest_entry_raw.get("landing_markdown"))
    if landing_markdown_path is None and bundle_dir is not None:
        landing_markdown_path = bundle_dir / "README.md"
    brief_json_path = _coerce_path(latest_entry_raw.get("brief_json"))
    if brief_json_path is None and bundle_dir is not None:
        brief_json_path = bundle_dir / "ops-brief.json"
    brief_markdown_path = _coerce_path(latest_entry_raw.get("brief_markdown"))
    if brief_markdown_path is None and bundle_dir is not None:
        brief_markdown_path = bundle_dir / "ops-brief.md"

    if bundle_json_path is None:
        return {
            "status": "missing",
            "path": None,
            "markdown_path": str(bundle_markdown_path) if bundle_markdown_path else None,
            "landing_html_path": str(landing_html_path) if landing_html_path else None,
            "landing_markdown_path": str(landing_markdown_path) if landing_markdown_path else None,
            "brief_json_path": str(brief_json_path) if brief_json_path else None,
            "brief_markdown_path": str(brief_markdown_path) if brief_markdown_path else None,
            "overall_status": None,
            "component_count": 0,
            "cross_link_count": 0,
            "component_statuses": {},
            "components": [],
            "cross_links": [],
            "error": "Latest index entry does not include a bundle manifest path.",
            "age_seconds": None,
            "age_human": "n/a",
        }
    if not bundle_json_path.exists():
        return {
            "status": "missing",
            "path": str(bundle_json_path),
            "markdown_path": str(bundle_markdown_path) if bundle_markdown_path else None,
            "landing_html_path": str(landing_html_path) if landing_html_path else None,
            "landing_markdown_path": str(landing_markdown_path) if landing_markdown_path else None,
            "brief_json_path": str(brief_json_path) if brief_json_path else None,
            "brief_markdown_path": str(brief_markdown_path) if brief_markdown_path else None,
            "overall_status": None,
            "component_count": 0,
            "cross_link_count": 0,
            "component_statuses": {},
            "components": [],
            "cross_links": [],
            "error": "Bundle manifest JSON is missing.",
            "age_seconds": None,
            "age_human": "n/a",
        }

    loaded_bundle = _load_json_file(bundle_json_path)
    if loaded_bundle["status"] != "available":
        return {
            "status": "invalid",
            "path": str(bundle_json_path),
            "markdown_path": str(bundle_markdown_path) if bundle_markdown_path else None,
            "landing_html_path": str(landing_html_path) if landing_html_path else None,
            "landing_markdown_path": str(landing_markdown_path) if landing_markdown_path else None,
            "brief_json_path": str(brief_json_path) if brief_json_path else None,
            "brief_markdown_path": str(brief_markdown_path) if brief_markdown_path else None,
            "overall_status": None,
            "component_count": 0,
            "cross_link_count": 0,
            "component_statuses": {},
            "components": [],
            "cross_links": [],
            "error": "Bundle manifest JSON could not be parsed.",
            "age_seconds": None,
            "age_human": "n/a",
        }

    payload = loaded_bundle["payload"]
    meta = _mapping(payload, "meta")
    summary = _mapping(payload, "summary")
    landing = _mapping(payload, "landing")
    components = _mapping(payload, "components")
    cross_links = [entry for entry in _list(payload.get("cross_links")) if isinstance(entry, dict)]
    age_seconds, age_human = _report_age_snapshot(
        rendered_at=rendered_at,
        generated_at=_string_or_none(meta.get("rendered_at")),
    )
    component_entries = [
        _serialize_bundle_component(key=key, payload=value)
        for key, value in sorted(components.items())
        if isinstance(value, dict)
    ]
    return {
        "status": "available",
        "path": str(bundle_json_path),
        "markdown_path": str(bundle_markdown_path) if bundle_markdown_path else None,
        "landing_html_path": _string_or_none(landing.get("html_path"))
        or (str(landing_html_path) if landing_html_path else None),
        "landing_markdown_path": _string_or_none(landing.get("markdown_path"))
        or (str(landing_markdown_path) if landing_markdown_path else None),
        "brief_json_path": str(brief_json_path) if brief_json_path else None,
        "brief_markdown_path": str(brief_markdown_path) if brief_markdown_path else None,
        "overall_status": _string_or_none(summary.get("overall_status")),
        "component_count": len(component_entries),
        "cross_link_count": len(cross_links),
        "component_statuses": dict(
            sorted(
                {
                    key: value
                    for key, value in _mapping(summary, "component_statuses").items()
                    if isinstance(value, str)
                }.items()
            )
        ),
        "components": component_entries,
        "cross_links": [
            {
                "source": _string_or_none(entry.get("source")) or "unknown",
                "target": _string_or_none(entry.get("target")) or "unknown",
                "status": _string_or_none(entry.get("status")) or "unknown",
                "reason": _string_or_none(entry.get("reason")) or "n/a",
            }
            for entry in cross_links
        ],
        "error": None,
        "age_seconds": age_seconds,
        "age_human": age_human,
    }


def _serialize_bundle_component(*, key: str, payload: dict[str, Any]) -> dict[str, Any]:
    output_paths = {
        name: value
        for name, value in sorted(_mapping(payload, "output_paths").items())
        if isinstance(value, str)
    }
    metrics = {
        metric_key: metric_value
        for metric_key, metric_value in sorted(payload.items())
        if metric_key not in {"status", "output_paths", "reason"}
    }
    summary = _summarize_metrics(metrics)
    reason = _string_or_none(payload.get("reason"))
    if reason and summary == "none":
        summary = reason
    return {
        "key": key,
        "status": _string_or_none(payload.get("status")) or "unknown",
        "summary": summary,
        "reason": reason,
        "metrics": metrics,
        "output_paths": output_paths,
    }


def _summarize_metrics(metrics: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in metrics.items():
        if isinstance(value, dict):
            continue
        parts.append(f"{key}={_format_scalar(value)}")
        if len(parts) == 4:
            break
    return ", ".join(parts) if parts else "none"


def _serialize_index_entry(entry: dict[str, Any], *, rendered_at: str) -> dict[str, Any]:
    rendered_value = _string_or_none(entry.get("rendered_at"))
    age_seconds, age_human = _report_age_snapshot(
        rendered_at=rendered_at,
        generated_at=rendered_value,
    )
    archive = _mapping(entry, "archive")
    archive_path = _string_or_none(archive.get("path"))
    component_statuses = {
        key: value
        for key, value in sorted(_mapping(entry, "component_statuses").items())
        if isinstance(value, str)
    }
    return {
        "entry_id": _string_or_none(entry.get("entry_id")) or "unknown",
        "rendered_at": rendered_value or "n/a",
        "age_seconds": age_seconds,
        "age_human": age_human,
        "overall_status": _string_or_none(entry.get("overall_status")) or "unknown",
        "brief_severity": _string_or_none(entry.get("brief_severity")) or "unknown",
        "brief_headline": _string_or_none(entry.get("brief_headline")) or "n/a",
        "brief_top_finding_count": int(entry.get("brief_top_finding_count", 0) or 0),
        "brief_next_action_count": int(entry.get("brief_next_action_count", 0) or 0),
        "issue_filter": entry.get("issue_filter"),
        "tracker_filter": entry.get("tracker_filter"),
        "bundle_dir": _string_or_none(entry.get("bundle_dir")) or "n/a",
        "bundle_relative_dir": _string_or_none(entry.get("bundle_relative_dir")) or "n/a",
        "bundle_json": _string_or_none(entry.get("bundle_json")),
        "bundle_markdown": _string_or_none(entry.get("bundle_markdown")),
        "landing_html": _string_or_none(entry.get("landing_html")),
        "landing_markdown": _string_or_none(entry.get("landing_markdown")),
        "brief_json": _string_or_none(entry.get("brief_json")),
        "brief_markdown": _string_or_none(entry.get("brief_markdown")),
        "archive_path": archive_path,
        "has_archive": bool(archive_path),
        "archive": archive if archive else None,
        "component_statuses": component_statuses,
    }


def _render_index_entry_markdown(entry: dict[str, Any]) -> list[str]:
    lines = [
        f"- entry_id: {entry.get('entry_id', '-')}",
        f"- rendered_at: {entry.get('rendered_at', '-')}",
        f"- age_human: {entry.get('age_human', '-')}",
        f"- overall_status: {entry.get('overall_status', '-')}",
        f"- brief_severity: {entry.get('brief_severity', '-')}",
        f"- brief_headline: {entry.get('brief_headline', '-')}",
        f"- brief_top_finding_count: {entry.get('brief_top_finding_count', 0)}",
        f"- brief_next_action_count: {entry.get('brief_next_action_count', 0)}",
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
        f"- archive_path: {entry.get('archive_path', '-')}",
    ]
    component_statuses = _mapping(entry, "component_statuses")
    if component_statuses:
        lines.append("- component_statuses:")
        lines.extend(f"  - {name}: {status}" for name, status in component_statuses.items())
    return lines


def _combine_index_status(latest_status: str, history_status: str) -> str:
    statuses = {latest_status, history_status}
    if statuses == {"missing"}:
        return "missing"
    if statuses == {"available"}:
        return "available"
    if "available" not in statuses and "invalid" in statuses:
        return "invalid"
    return "partial"


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "payload": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "invalid", "payload": {}}
    if not isinstance(payload, dict):
        return {"status": "invalid", "payload": {}}
    return {"status": "available", "payload": payload}


def _entry_has_archive(entry: dict[str, Any]) -> bool:
    archive = entry.get("archive")
    return isinstance(archive, dict) and bool(_string_or_none(archive.get("path")))


def _report_age_snapshot(*, rendered_at: str, generated_at: str | None) -> tuple[int | None, str]:
    rendered_dt = _parse_iso_datetime(rendered_at)
    generated_dt = _parse_iso_datetime(generated_at)
    if rendered_dt is None or generated_dt is None:
        return None, "n/a"
    age_seconds = int((rendered_dt - generated_dt).total_seconds())
    if age_seconds < -60:
        return age_seconds, f"in {_format_age_seconds(abs(age_seconds))}"
    normalized_age = max(age_seconds, 0)
    return normalized_age, _format_age_seconds(normalized_age)


def _format_age_seconds(value: int) -> str:
    days, remainder = divmod(value, 86_400)
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


def _coerce_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).expanduser().resolve()


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _format_scalar(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)
