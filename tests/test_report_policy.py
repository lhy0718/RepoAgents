from __future__ import annotations

from pathlib import Path

from repoagents.config import load_config
from repoagents.report_policy import (
    build_report_freshness_policy_snapshot,
    build_report_policy_alignment,
    build_report_policy_drift_guidance,
    extract_embedded_report_policy,
)


def test_build_report_policy_drift_guidance_returns_summary_and_detail() -> None:
    guidance = build_report_policy_drift_guidance()

    assert guidance["summary"] == "refresh raw report exports to align embedded policy metadata"
    assert "`repoagents sync audit --format all`" in guidance["detail"]
    assert "`repoagents clean --report --report-format all`" in guidance["detail"]


def test_build_report_freshness_policy_snapshot_matches_loaded_config(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)

    snapshot = build_report_freshness_policy_snapshot(loaded)
    policy = loaded.data.dashboard.report_freshness_policy

    assert snapshot["summary"] == (
        f"unknown>={policy.unknown_issues_threshold} "
        f"stale>={policy.stale_issues_threshold} "
        f"future>={policy.future_attention_threshold} "
        f"aging>={policy.aging_attention_threshold}"
    )
    assert snapshot["report_freshness_policy"] == {
        "unknown_issues_threshold": policy.unknown_issues_threshold,
        "stale_issues_threshold": policy.stale_issues_threshold,
        "future_attention_threshold": policy.future_attention_threshold,
        "aging_attention_threshold": policy.aging_attention_threshold,
    }


def test_extract_embedded_report_policy_returns_expected_policy_mapping() -> None:
    assert extract_embedded_report_policy(None) == {}
    assert extract_embedded_report_policy({"policy": "invalid"}) == {}
    assert extract_embedded_report_policy(
        {
            "policy": {
                "summary": "unknown>=2 stale>=2 future>=2 aging>=2",
                "report_freshness_policy": {
                    "unknown_issues_threshold": 2,
                    "stale_issues_threshold": 2,
                    "future_attention_threshold": 2,
                    "aging_attention_threshold": 2,
                },
            }
        }
    ) == {
        "summary": "unknown>=2 stale>=2 future>=2 aging>=2",
        "report_freshness_policy": {
            "unknown_issues_threshold": 2,
            "stale_issues_threshold": 2,
            "future_attention_threshold": 2,
            "aging_attention_threshold": 2,
        },
    }


def test_build_report_policy_alignment_handles_match_drift_and_missing() -> None:
    current_policy = {
        "summary": "unknown>=2 stale>=2 future>=2 aging>=2",
        "report_freshness_policy": {
            "unknown_issues_threshold": 2,
            "stale_issues_threshold": 2,
            "future_attention_threshold": 2,
            "aging_attention_threshold": 2,
        },
    }

    match = build_report_policy_alignment(
        current_policy=current_policy,
        payload={"policy": current_policy},
    )
    assert match["status"] == "match"
    assert match["remediation"] is None

    drift = build_report_policy_alignment(
        current_policy=current_policy,
        payload={
            "policy": {
                "summary": "unknown>=1 stale>=1 future>=1 aging>=1",
                "report_freshness_policy": {
                    "unknown_issues_threshold": 1,
                    "stale_issues_threshold": 1,
                    "future_attention_threshold": 1,
                    "aging_attention_threshold": 1,
                },
            }
        },
    )
    assert drift["status"] == "drift"
    assert drift["embedded_summary"] == "unknown>=1 stale>=1 future>=1 aging>=1"
    assert drift["remediation"] == build_report_policy_drift_guidance()["detail"]

    missing = build_report_policy_alignment(
        current_policy=current_policy,
        payload={},
    )
    assert missing["status"] == "missing"
    assert missing["embedded_summary"] is None
    assert missing["remediation"] is None
