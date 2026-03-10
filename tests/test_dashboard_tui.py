from __future__ import annotations

from repoagents.config import load_config
from repoagents.dashboard_tui import (
    DashboardTuiAction,
    DashboardTuiEntry,
    build_dashboard_tui_model,
    execute_dashboard_tui_action,
)
from repoagents.models import RunLifecycle, RunRecord
from repoagents.orchestrator import RunStateStore


def test_build_dashboard_tui_model_groups_snapshot_into_sections() -> None:
    snapshot = {
        "meta": {
            "repo_name": "demo-repo",
            "rendered_at": "2026-03-10T12:00:00+00:00",
            "last_updated": "2026-03-10T11:58:00+00:00",
        },
        "hero": {
            "title": "Report freshness needs action",
            "severity": "issues",
            "summary": "Two reports are stale and one run failed.",
        },
        "counts": {
            "visible_runs": 1,
            "total_runs": 3,
            "visible_sync_handoffs": 1,
            "policy_drift_reports": 2,
        },
        "runs": [
            {
                "issue_id": 7,
                "issue_title": "Fix parser edge case",
                "run_id": "run-7",
                "status": "failed",
                "attempts": 2,
                "backend_mode": "codex",
                "summary": "Reviewer requested more tests.",
                "last_error": "Missing regression coverage.",
                "updated_at": "2026-03-10T11:57:00+00:00",
                "workspace_path": "/tmp/demo/workspace",
                "artifacts": [{"label": "reviewer"}],
                "external_actions": [{"action": "post_comment"}],
            }
        ],
        "reports": {
            "total": 2,
            "entries": [
                {
                    "key": "github-smoke",
                    "label": "GitHub smoke",
                    "status": "attention",
                    "freshness_status": "stale",
                    "age_human": "2h 0m",
                    "summary": "publish=warn branch_policy=warn",
                    "policy_alignment_note": "embedded policy differs from current config",
                    "related_report_detail_summary": "1 mismatch, 2 policy drifts",
                    "metrics": {"open_issue_count": 3, "publish_status": "warn"},
                    "json_path": "/tmp/demo/reports/github-smoke.json",
                    "markdown_path": "/tmp/demo/reports/github-smoke.md",
                }
            ],
        },
        "ops_snapshots": {
            "history_entry_count": 2,
            "archive_entry_count": 1,
            "latest": {
                "entry_id": "20260310T115700Z",
                "overall_status": "attention",
                "brief_severity": "attention",
                "brief_headline": "GitHub publish is still gated.",
                "age_human": "3m",
                "bundle_dir": "/tmp/demo/ops/20260310T115700Z",
                "component_statuses": {"doctor": "clean", "github_smoke": "attention"},
                "archive_path": "/tmp/demo/ops/20260310T115700Z.tar.gz",
            },
            "entries": [],
        },
        "sync_handoffs": [
            {
                "issue_id": 7,
                "action": "pr-body",
                "tracker": "local-markdown",
                "summary": "Draft PR body archived for handoff.",
                "artifact_role": "pr-body-proposal",
                "bundle_key": "issue:7|head:repoagents/issue-7",
                "applied_at": "2026-03-10T11:56:00+00:00",
                "staged_at": "20260310T115600Z",
                "archived_path": "/tmp/demo/sync/20260310T115600Z-pr-body.md",
                "manifest_path": "/tmp/demo/sync/manifest.json",
            }
        ],
        "sync_retention": {
            "total_issues": 1,
            "entries": [
                {
                    "tracker": "local-markdown",
                    "issue_id": 7,
                    "status": "prunable",
                    "keep_groups_limit": 1,
                    "integrity_findings": 0,
                    "total_groups": 2,
                    "prunable_groups": 1,
                    "prunable_bytes_human": "4.0 KB",
                    "oldest_prunable_group_age_human": "2d 3h",
                    "groups": [
                        {
                            "status": "prunable",
                            "group_key": "issue:7|head:repoagents/issue-7",
                        }
                    ],
                }
            ],
        },
    }

    model = build_dashboard_tui_model(snapshot)

    assert model.title == "RepoAgents TUI | demo-repo"
    assert "Report freshness needs action" in model.subtitle
    assert len(model.sections) == 5
    assert [section.label for section in model.sections] == [
        "Runs",
        "Reports",
        "Ops",
        "Handoffs",
        "Retention",
    ]
    assert model.sections[0].entries[0].title == "#7 Fix parser edge case"
    assert model.sections[0].entries[0].actions[0].key == "retry_issue"
    assert any(
        "Missing regression coverage." in detail
        for detail in model.sections[0].entries[0].details
    )
    assert model.sections[1].entries[0].title == "GitHub smoke"
    assert model.sections[1].entries[0].actions[0].key == "refresh_report"
    assert "policy:" in model.sections[1].entries[0].details[3]
    assert model.sections[2].entries[0].title == "Latest 20260310T115700Z"
    assert model.sections[3].entries[0].title == "#7 pr-body"
    assert model.sections[4].entries[0].title == "local-markdown / issue-7"


def test_execute_dashboard_tui_action_retries_issue(demo_repo) -> None:
    loaded = load_config(demo_repo)
    store = RunStateStore(loaded.state_dir / "runs.json")
    store.upsert(
        RunRecord(
            run_id="run-7",
            issue_id=7,
            issue_title="Fix parser edge case",
            fingerprint="fp-7",
            status=RunLifecycle.FAILED,
            backend_mode="codex",
        )
    )

    message = execute_dashboard_tui_action(
        loaded,
        section_key="runs",
        entry=DashboardTuiEntry(
            title="#7 Fix parser edge case",
            subtitle="failed | attempts=1",
            status="failed",
            details=(),
            actions=(
                DashboardTuiAction(
                    key="retry_issue",
                    label="Retry issue #7",
                    confirmation_prompt="Schedule issue #7 for immediate retry? [y/N]",
                ),
            ),
            context={"issue_id": 7},
        ),
        action=DashboardTuiAction(
            key="retry_issue",
            label="Retry issue #7",
            confirmation_prompt="Schedule issue #7 for immediate retry? [y/N]",
        ),
        limit=25,
    )

    updated = RunStateStore(loaded.state_dir / "runs.json").get(7)
    assert message == "Issue #7 scheduled for immediate retry."
    assert updated is not None
    assert updated.status == RunLifecycle.RETRY_PENDING


def test_execute_dashboard_tui_action_refreshes_sync_audit_report(demo_repo) -> None:
    loaded = load_config(demo_repo)

    message = execute_dashboard_tui_action(
        loaded,
        section_key="reports",
        entry=DashboardTuiEntry(
            title="Sync audit",
            subtitle="attention | stale | age=n/a",
            status="attention",
            details=(),
            actions=(DashboardTuiAction(key="refresh_report", label="Refresh Sync audit"),),
            context={"report_key": "sync-audit", "label": "Sync audit"},
        ),
        action=DashboardTuiAction(key="refresh_report", label="Refresh Sync audit"),
        limit=25,
    )

    assert message == "Refreshed Sync audit report."
    assert (loaded.reports_dir / "sync-audit.json").exists()
    assert (loaded.reports_dir / "sync-audit.md").exists()
