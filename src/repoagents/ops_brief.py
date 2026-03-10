from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repoagents.models.domain import utc_now
from repoagents.utils.files import write_text_file


VALID_OPS_BRIEF_FORMATS = ("json", "markdown")


@dataclass(frozen=True, slots=True)
class OpsBriefBuildResult:
    output_paths: dict[str, Path]
    snapshot: dict[str, Any]
    severity: str
    headline: str
    top_finding_count: int
    next_action_count: int


def normalize_ops_brief_formats(
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
            for item in VALID_OPS_BRIEF_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_OPS_BRIEF_FORMATS:
            raise ValueError("Unsupported ops brief format. Expected one of: json, markdown, all")
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def resolve_ops_brief_export_paths(
    target: Path,
    formats: tuple[str, ...],
) -> dict[str, Path]:
    resolved = target.resolve()
    export_paths: dict[str, Path] = {}
    for export_format in formats:
        suffix = ".md" if export_format == "markdown" else ".json"
        export_paths[export_format] = resolved.with_suffix(suffix)
    return export_paths


def build_ops_brief_snapshot(
    *,
    repo_root: Path,
    config_path: Path,
    issue_filter: int | None,
    tracker_filter: str | None,
    doctor_snapshot: dict[str, Any],
    status_snapshot: dict[str, Any],
    dashboard_snapshot: dict[str, Any],
    sync_audit_snapshot: dict[str, Any],
    sync_health_snapshot: dict[str, Any],
    github_smoke_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rendered_at = utc_now().isoformat()
    doctor_summary = _mapping(doctor_snapshot, "summary")
    status_summary = _mapping(status_snapshot, "summary")
    report_health = _mapping(status_snapshot, "report_health")
    hero = _mapping(report_health, "hero")
    policy = _mapping(report_health, "policy")
    sync_audit_summary = _mapping(sync_audit_snapshot, "summary")
    sync_health_summary = _mapping(sync_health_snapshot, "summary")
    github_smoke_summary = _mapping(github_smoke_snapshot or {}, "summary")
    github_smoke_publish = _mapping(github_smoke_snapshot or {}, "publish")
    github_smoke_branch_policy = _mapping(github_smoke_snapshot or {}, "branch_policy")

    severity = _combine_severities(
        _normalize_severity(doctor_summary.get("overall_status")),
        _normalize_severity(hero.get("severity")),
        _normalize_severity(sync_audit_summary.get("overall_status")),
        _normalize_severity(sync_health_summary.get("overall_status")),
        _normalize_optional_severity(github_smoke_summary.get("status")),
    )
    top_findings = _build_top_findings(
        doctor_summary=doctor_summary,
        hero=hero,
        sync_audit_summary=sync_audit_summary,
        sync_health_summary=sync_health_summary,
        github_smoke_summary=github_smoke_summary,
        github_smoke_publish=github_smoke_publish,
        github_smoke_branch_policy=github_smoke_branch_policy,
    )
    next_actions = _build_next_actions(
        doctor_summary=doctor_summary,
        hero=hero,
        sync_health_summary=sync_health_summary,
        github_smoke_summary=github_smoke_summary,
        github_smoke_publish=github_smoke_publish,
    )
    title = _brief_title(severity)
    headline = _brief_headline(
        severity=severity,
        top_findings=top_findings,
        next_actions=next_actions,
    )

    return {
        "meta": {
            "rendered_at": rendered_at,
            "repo_root": str(repo_root),
            "config_path": str(config_path),
            "issue_filter": issue_filter,
            "tracker_filter": tracker_filter,
        },
        "summary": {
            "severity": severity,
            "title": title,
            "headline": headline,
            "top_finding_count": len(top_findings),
            "next_action_count": len(next_actions),
            "selected_runs": int(status_summary.get("selected_runs", 0) or 0),
            "report_health_severity": _string_or_none(hero.get("severity")) or "unknown",
            "sync_audit_status": _string_or_none(sync_audit_summary.get("overall_status")) or "unknown",
            "sync_health_status": _string_or_none(sync_health_summary.get("overall_status")) or "unknown",
            "github_smoke_status": _string_or_none(github_smoke_summary.get("status")) or "not_applicable",
        },
        "policy": {
            "summary": _string_or_none(policy.get("summary")),
            "report_freshness_policy": dict(_mapping(policy, "report_freshness_policy")),
        },
        "top_findings": top_findings,
        "next_actions": next_actions,
        "related_reports": {
            "entries": _build_related_reports(
                severity=severity,
                sync_audit_summary=sync_audit_summary,
                sync_health_summary=sync_health_summary,
                github_smoke_summary=github_smoke_summary,
            ),
        },
        "sources": {
            "doctor": {
                "overall_status": doctor_summary.get("overall_status"),
                "diagnostic_count": doctor_summary.get("diagnostic_count", 0),
                "exit_code": doctor_summary.get("exit_code", 1),
            },
            "status": {
                "total_runs": status_summary.get("total_runs", 0),
                "selected_runs": status_summary.get("selected_runs", 0),
            },
            "report_health": {
                "severity": hero.get("severity"),
                "title": hero.get("title"),
                "summary": hero.get("summary"),
            },
            "dashboard": {
                "hero_severity": _mapping(dashboard_snapshot, "hero").get("severity"),
                "report_count": len(_list(_mapping(dashboard_snapshot, "reports").get("entries"))),
            },
            "sync_audit": {
                "overall_status": sync_audit_summary.get("overall_status"),
                "pending_artifacts": sync_audit_summary.get("pending_artifacts", 0),
                "integrity_issue_count": sync_audit_summary.get("integrity_issue_count", 0),
                "repair_needed_issues": sync_audit_summary.get("repair_needed_issues", 0),
            },
            "sync_health": {
                "overall_status": sync_health_summary.get("overall_status"),
                "pending_artifacts": sync_health_summary.get("pending_artifacts", 0),
                "integrity_issue_count": sync_health_summary.get("integrity_issue_count", 0),
                "repair_changed_reports": sync_health_summary.get("repair_changed_reports", 0),
                "cleanup_action_count": sync_health_summary.get("cleanup_action_count", 0),
                "related_report_mismatches": sync_health_summary.get("related_report_mismatches", 0),
                "related_report_policy_drifts": sync_health_summary.get("related_report_policy_drifts", 0),
            },
            "github_smoke": {
                "status": github_smoke_summary.get("status"),
                "open_issue_count": github_smoke_summary.get("open_issue_count", 0),
                "sampled_issue_id": github_smoke_summary.get("sampled_issue_id"),
                "publish_status": github_smoke_publish.get("status"),
                "branch_policy_status": github_smoke_branch_policy.get("status"),
            },
        },
    }


def build_ops_brief_exports(
    *,
    snapshot: dict[str, Any],
    output_path: Path,
    formats: tuple[str, ...],
) -> OpsBriefBuildResult:
    export_paths = resolve_ops_brief_export_paths(output_path, formats)
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_ops_brief_json(snapshot))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_ops_brief_markdown(snapshot))
    summary = _mapping(snapshot, "summary")
    return OpsBriefBuildResult(
        output_paths=export_paths,
        snapshot=snapshot,
        severity=_string_or_none(summary.get("severity")) or "attention",
        headline=_string_or_none(summary.get("headline")) or "Ops handoff summary available.",
        top_finding_count=int(summary.get("top_finding_count", 0) or 0),
        next_action_count=int(summary.get("next_action_count", 0) or 0),
    )


def render_ops_brief_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True)


def render_ops_brief_markdown(snapshot: dict[str, Any]) -> str:
    meta = _mapping(snapshot, "meta")
    summary = _mapping(snapshot, "summary")
    policy = _mapping(snapshot, "policy")
    top_findings = _list_of_strings(snapshot.get("top_findings"))
    next_actions = _list_of_strings(snapshot.get("next_actions"))
    related_reports = _mapping(snapshot, "related_reports")
    sources = _mapping(snapshot, "sources")

    lines = [
        "# RepoAgents Ops Brief",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- config_path: {meta.get('config_path', '-')}",
        f"- issue_filter: {meta.get('issue_filter') if meta.get('issue_filter') is not None else 'all'}",
        f"- tracker_filter: {meta.get('tracker_filter') or 'all'}",
        "",
        "## Summary",
        f"- severity: {summary.get('severity', '-')}",
        f"- title: {summary.get('title', '-')}",
        f"- headline: {summary.get('headline', '-')}",
        f"- top_finding_count: {summary.get('top_finding_count', 0)}",
        f"- next_action_count: {summary.get('next_action_count', 0)}",
        f"- selected_runs: {summary.get('selected_runs', 0)}",
        f"- report_health_severity: {summary.get('report_health_severity', '-')}",
        f"- sync_audit_status: {summary.get('sync_audit_status', '-')}",
        f"- sync_health_status: {summary.get('sync_health_status', '-')}",
        f"- github_smoke_status: {summary.get('github_smoke_status', '-')}",
        "",
        "## Policy",
        f"- summary: {policy.get('summary', '-')}",
        f"- thresholds: {_render_mapping(_mapping(policy, 'report_freshness_policy'))}",
        "",
        "## Top findings",
    ]
    if top_findings:
        lines.extend(f"- {item}" for item in top_findings)
    else:
        lines.append("- No notable findings.")

    lines.extend(["", "## Next actions"])
    if next_actions:
        lines.extend(f"- {item}" for item in next_actions)
    else:
        lines.append("- No immediate follow-up actions.")

    lines.extend(["", "## Related reports"])
    related_entries = [item for item in _list(related_reports.get("entries")) if isinstance(item, dict)]
    if related_entries:
        for entry in related_entries:
            lines.append(
                f"- {entry.get('label', entry.get('key', 'related'))}: "
                f"status={entry.get('status', '-')} "
                f"warning={entry.get('warning') or 'none'}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Sources"])
    for key, payload in sources.items():
        if not isinstance(payload, dict):
            continue
        lines.append(f"- {key}: {_render_mapping(payload)}")
    return "\n".join(lines) + "\n"


def _build_top_findings(
    *,
    doctor_summary: dict[str, Any],
    hero: dict[str, Any],
    sync_audit_summary: dict[str, Any],
    sync_health_summary: dict[str, Any],
    github_smoke_summary: dict[str, Any],
    github_smoke_publish: dict[str, Any],
    github_smoke_branch_policy: dict[str, Any],
) -> list[str]:
    findings: list[str] = []
    if int(doctor_summary.get("exit_code", 0) or 0) != 0:
        findings.append("Doctor still reports failing diagnostics in the current repo setup.")
    hero_title = _string_or_none(hero.get("title"))
    hero_summary = _string_or_none(hero.get("summary"))
    if _normalize_severity(hero.get("severity")) in {"attention", "issues"}:
        if hero_title:
            findings.append(f"Report health: {hero_title}.")
        elif hero_summary:
            findings.append(f"Report health: {hero_summary}.")
    pending_artifacts = int(sync_health_summary.get("pending_artifacts", 0) or 0)
    if pending_artifacts > 0:
        findings.append(f"Sync health found {pending_artifacts} pending staged artifact(s).")
    integrity_issue_count = int(sync_health_summary.get("integrity_issue_count", 0) or 0)
    if integrity_issue_count > 0:
        findings.append(f"Sync health found {integrity_issue_count} applied manifest integrity issue(s).")
    cleanup_action_count = int(sync_health_summary.get("cleanup_action_count", 0) or 0)
    if cleanup_action_count > 0:
        findings.append(f"Cleanup preview would remove {cleanup_action_count} stale runtime path(s).")
    repair_changed_reports = int(sync_health_summary.get("repair_changed_reports", 0) or 0)
    if repair_changed_reports > 0:
        findings.append(f"Sync repair preview would rewrite {repair_changed_reports} manifest report(s).")
    related_report_policy_drifts = int(sync_health_summary.get("related_report_policy_drifts", 0) or 0)
    if related_report_policy_drifts > 0:
        findings.append(
            f"Related sync reports show {related_report_policy_drifts} policy drift warning(s)."
        )
    github_smoke_status = _normalize_optional_severity(github_smoke_summary.get("status"))
    if github_smoke_status in {"attention", "issues"}:
        publish_message = _string_or_none(github_smoke_publish.get("message"))
        branch_policy_message = _string_or_none(github_smoke_branch_policy.get("message"))
        if publish_message:
            findings.append(f"GitHub publish readiness: {publish_message}.")
        elif branch_policy_message:
            findings.append(f"GitHub branch policy: {branch_policy_message}.")
    sync_audit_integrity = int(sync_audit_summary.get("integrity_issue_count", 0) or 0)
    if sync_audit_integrity > 0 and sync_audit_integrity != integrity_issue_count:
        findings.append(f"Sync audit still reports {sync_audit_integrity} integrity issue(s).")
    return _dedupe(findings)[:5]


def _build_next_actions(
    *,
    doctor_summary: dict[str, Any],
    hero: dict[str, Any],
    sync_health_summary: dict[str, Any],
    github_smoke_summary: dict[str, Any],
    github_smoke_publish: dict[str, Any],
) -> list[str]:
    actions = _list_of_strings(sync_health_summary.get("next_actions"))
    if int(doctor_summary.get("exit_code", 0) or 0) != 0:
        actions.append("Run `repoagents doctor` and resolve any failing diagnostics before live publish.")
    if _normalize_severity(hero.get("severity")) in {"attention", "issues"}:
        actions.append("Review dashboard report health and refresh stale or drifted raw report exports.")
    if _normalize_optional_severity(github_smoke_summary.get("status")) in {"attention", "issues"}:
        publish_message = _string_or_none(github_smoke_publish.get("message"))
        action = "Run `repoagents github smoke --require-write-ready` and clear GitHub branch/publish warnings before unattended live writes."
        if publish_message:
            action = (
                "Run `repoagents github smoke --require-write-ready` and resolve "
                f"the current GitHub publish warning set ({publish_message})."
            )
        actions.append(action)
    return _dedupe(actions)[:5]


def _build_related_reports(
    *,
    severity: str,
    sync_audit_summary: dict[str, Any],
    sync_health_summary: dict[str, Any],
    github_smoke_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    sync_audit_status = _string_or_none(sync_audit_summary.get("overall_status")) or "unknown"
    sync_health_status = _string_or_none(sync_health_summary.get("overall_status")) or "unknown"
    related_reports = [
        {
            "key": "ops-status",
            "label": "Ops status",
            "status": severity,
            "warning": None if severity == "clean" else "latest ops brief still needs follow-up",
        },
        {
            "key": "sync-audit",
            "label": "Sync audit",
            "status": sync_audit_status,
            "warning": None if sync_audit_status == "clean" else "latest sync audit is not clean",
        },
        {
            "key": "sync-health",
            "label": "Sync health",
            "status": sync_health_status,
            "warning": None if sync_health_status == "clean" else "latest sync health is not clean",
        },
    ]
    github_smoke_status = _string_or_none(github_smoke_summary.get("status")) or "not_applicable"
    if github_smoke_status != "not_applicable":
        related_reports.append(
            {
                "key": "github-smoke",
                "label": "GitHub smoke",
                "status": github_smoke_status,
                "warning": (
                    None
                    if github_smoke_status == "clean"
                    else "latest GitHub smoke still reports live publish warnings"
                ),
            }
        )
    return related_reports


def _brief_title(severity: str) -> str:
    if severity == "issues":
        return "Operator action required"
    if severity == "attention":
        return "Follow-up recommended"
    return "Handoff is clean"


def _brief_headline(
    *,
    severity: str,
    top_findings: list[str],
    next_actions: list[str],
) -> str:
    if top_findings:
        return top_findings[0]
    if severity == "clean":
        return "Current ops snapshot is clean and ready to hand off."
    if next_actions:
        return f"{len(next_actions)} follow-up action(s) remain for the current handoff."
    return "Current ops snapshot needs operator review."


def _combine_severities(*values: object) -> str:
    winner = "clean"
    for value in values:
        normalized = _normalize_severity(value)
        if normalized == "issues":
            return "issues"
        if normalized == "attention":
            winner = "attention"
    return winner


def _normalize_severity(value: object) -> str:
    lowered = str(value).strip().lower() if value is not None else ""
    if lowered in {"issues", "error", "failed", "fail"}:
        return "issues"
    if lowered in {"attention", "warning", "warn", "preview"}:
        return "attention"
    if lowered in {"clean", "ok", "available", "completed"}:
        return "clean"
    return "attention"


def _normalize_optional_severity(value: object) -> str:
    lowered = str(value).strip().lower() if value is not None else ""
    if not lowered or lowered in {"not_applicable", "n/a", "unknown", "none"}:
        return "clean"
    return _normalize_severity(value)


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _list_of_strings(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, str) and item]


def _list(items: object) -> list[Any]:
    if not isinstance(items, list):
        return []
    return items


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _render_mapping(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in payload.items():
        if isinstance(value, dict):
            continue
        parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else "n/a"


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
