from __future__ import annotations

from pathlib import Path

import pytest

from reporepublic.config import ConfigLoadError, load_config


def test_load_config_success(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    assert loaded.data.tracker.repo == "demo/repo"
    assert loaded.data.llm.mode.value == "mock"
    assert loaded.workspace_root == (demo_repo / ".ai-republic" / "workspaces").resolve()
    assert loaded.logs_dir == (demo_repo / ".ai-republic" / "logs").resolve()
    assert loaded.data.agent.debug_artifacts is False
    assert loaded.data.logging.file_enabled is False
    assert loaded.data.cleanup.sync_applied_keep_groups_per_issue == 20
    assert loaded.data.cleanup.ops_snapshot_keep_entries == 25
    assert loaded.data.cleanup.ops_snapshot_prune_managed is False
    assert loaded.data.dashboard.report_freshness_policy.stale_issues_threshold == 1


def test_load_config_local_file_tracker_success(tmp_path: Path) -> None:
    ai_root = tmp_path / ".ai-republic"
    ai_root.mkdir(parents=True)
    (ai_root / "reporepublic.yaml").write_text(
        "tracker:\n  kind: local_file\n  path: issues.json\n",
        encoding="utf-8",
    )

    loaded = load_config(tmp_path)

    assert loaded.data.tracker.kind.value == "local_file"
    assert loaded.data.tracker.path == "issues.json"
    assert loaded.data.tracker.repo is None


def test_load_config_validation_error(tmp_path: Path) -> None:
    ai_root = tmp_path / ".ai-republic"
    ai_root.mkdir(parents=True)
    (ai_root / "reporepublic.yaml").write_text(
        "tracker:\n  kind: github\n  repo: invalid\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError) as excinfo:
        load_config(tmp_path)
    assert "tracker.repo" in str(excinfo.value)


def test_load_config_local_file_requires_path(tmp_path: Path) -> None:
    ai_root = tmp_path / ".ai-republic"
    ai_root.mkdir(parents=True)
    (ai_root / "reporepublic.yaml").write_text(
        "tracker:\n  kind: local_file\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigLoadError) as excinfo:
        load_config(tmp_path)

    assert "tracker.path" in str(excinfo.value)


def test_load_config_accepts_optional_qa_role_between_engineer_and_reviewer(tmp_path: Path) -> None:
    ai_root = tmp_path / ".ai-republic"
    ai_root.mkdir(parents=True)
    (ai_root / "reporepublic.yaml").write_text(
        "\n".join(
            [
                "tracker:",
                "  kind: github",
                "  repo: demo/repo",
                "roles:",
                "  enabled:",
                "    - triage",
                "    - planner",
                "    - engineer",
                "    - qa",
                "    - reviewer",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_config(tmp_path)

    assert [role.value for role in loaded.data.roles.enabled] == [
        "triage",
        "planner",
        "engineer",
        "qa",
        "reviewer",
    ]


def test_load_config_rejects_qa_outside_supported_order(tmp_path: Path) -> None:
    ai_root = tmp_path / ".ai-republic"
    ai_root.mkdir(parents=True)
    (ai_root / "reporepublic.yaml").write_text(
        "\n".join(
            [
                "tracker:",
                "  kind: github",
                "  repo: demo/repo",
                "roles:",
                "  enabled:",
                "    - triage",
                "    - planner",
                "    - qa",
                "    - engineer",
                "    - reviewer",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigLoadError) as excinfo:
        load_config(tmp_path)

    assert "roles.enabled" in str(excinfo.value)


def test_load_config_accepts_cleanup_sync_retention_override(tmp_path: Path) -> None:
    ai_root = tmp_path / ".ai-republic"
    ai_root.mkdir(parents=True)
    (ai_root / "reporepublic.yaml").write_text(
        "\n".join(
            [
                "tracker:",
                "  kind: github",
                "  repo: demo/repo",
                "cleanup:",
                "  sync_applied_keep_groups_per_issue: 7",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_config(tmp_path)

    assert loaded.data.cleanup.sync_applied_keep_groups_per_issue == 7


def test_load_config_accepts_ops_snapshot_cleanup_override(tmp_path: Path) -> None:
    ai_root = tmp_path / ".ai-republic"
    ai_root.mkdir(parents=True)
    (ai_root / "reporepublic.yaml").write_text(
        "\n".join(
            [
                "tracker:",
                "  kind: github",
                "  repo: demo/repo",
                "cleanup:",
                "  ops_snapshot_keep_entries: 3",
                "  ops_snapshot_prune_managed: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_config(tmp_path)

    assert loaded.data.cleanup.ops_snapshot_keep_entries == 3
    assert loaded.data.cleanup.ops_snapshot_prune_managed is True


def test_load_config_accepts_dashboard_report_freshness_policy_override(tmp_path: Path) -> None:
    ai_root = tmp_path / ".ai-republic"
    ai_root.mkdir(parents=True)
    (ai_root / "reporepublic.yaml").write_text(
        "\n".join(
            [
                "tracker:",
                "  kind: github",
                "  repo: demo/repo",
                "dashboard:",
                "  report_freshness_policy:",
                "    stale_issues_threshold: 2",
                "    unknown_issues_threshold: 3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_config(tmp_path)

    assert loaded.data.dashboard.report_freshness_policy.stale_issues_threshold == 2
    assert loaded.data.dashboard.report_freshness_policy.unknown_issues_threshold == 3
