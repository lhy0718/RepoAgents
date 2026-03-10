from __future__ import annotations

from repoagents.config import LoadedConfig


def build_report_policy_drift_guidance() -> dict[str, str]:
    summary = "refresh raw report exports to align embedded policy metadata"
    return {
        "summary": summary,
        "detail": (
            f"{summary}; re-run `repoagents sync audit --format all` and "
            "`repoagents clean --report --report-format all` after updating "
            "`dashboard.report_freshness_policy`"
        ),
    }


def build_report_freshness_policy_snapshot(loaded: LoadedConfig) -> dict[str, object]:
    policy = loaded.data.dashboard.report_freshness_policy
    return {
        "summary": (
            f"unknown>={policy.unknown_issues_threshold} "
            f"stale>={policy.stale_issues_threshold} "
            f"future>={policy.future_attention_threshold} "
            f"aging>={policy.aging_attention_threshold}"
        ),
        "report_freshness_policy": {
            "unknown_issues_threshold": policy.unknown_issues_threshold,
            "stale_issues_threshold": policy.stale_issues_threshold,
            "future_attention_threshold": policy.future_attention_threshold,
            "aging_attention_threshold": policy.aging_attention_threshold,
        },
    }


def build_report_policy_alignment(
    *,
    current_policy: dict[str, object],
    payload: dict[str, object] | None,
) -> dict[str, object]:
    current_summary = _string_or_none(current_policy.get("summary"))
    current_thresholds = current_policy.get("report_freshness_policy")
    if not isinstance(current_thresholds, dict):
        current_thresholds = {}

    embedded_policy = extract_embedded_report_policy(payload)
    embedded_summary = _string_or_none(embedded_policy.get("summary"))
    embedded_thresholds = embedded_policy.get("report_freshness_policy")
    if not isinstance(embedded_thresholds, dict):
        embedded_thresholds = {}

    if embedded_summary is None:
        status = "missing"
        warning = "raw report export did not embed policy metadata"
        remediation = None
    elif embedded_summary == current_summary:
        status = "match"
        warning = "embedded policy matches current config"
        remediation = None
    else:
        status = "drift"
        warning = f"embedded policy differs from current config ({embedded_summary})"
        remediation = build_report_policy_drift_guidance()["detail"]

    return {
        "status": status,
        "warning": warning,
        "remediation": remediation,
        "current_summary": current_summary,
        "current_report_freshness_policy": dict(current_thresholds),
        "embedded_summary": embedded_summary,
        "embedded_report_freshness_policy": dict(embedded_thresholds),
    }


def extract_embedded_report_policy(payload: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    policy = payload.get("policy")
    if not isinstance(policy, dict):
        return {}
    thresholds = policy.get("report_freshness_policy")
    if not isinstance(thresholds, dict):
        thresholds = {}
    return {
        "summary": _string_or_none(policy.get("summary")),
        "report_freshness_policy": dict(thresholds),
    }


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
