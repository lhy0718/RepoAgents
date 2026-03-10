from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from repoagents.config import load_config
from repoagents.models import IssueRef
from repoagents.utils import run_git
from repoagents.workspace import WorkspaceError, WorktreeWorkspaceManager, build_workspace_manager

from conftest import create_demo_repo, initialize_git_repo


def test_workspace_copy_isolated(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    manager = build_workspace_manager(loaded)
    issue = IssueRef(id=1, title="Fix empty input crash")
    workspace = asyncio.run(manager.prepare_workspace(issue, "run-1"))
    assert (workspace / ".ai-repoagents" / "prompts" / "triage.txt.j2").exists()
    assert not (workspace / ".ai-repoagents" / "state").exists()
    assert (workspace / "parser.py").exists()


def test_workspace_worktree_strategy(tmp_path: Path) -> None:
    repo_root = initialize_git_repo(create_demo_repo(tmp_path / "repo"))
    config_path = repo_root / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("strategy: copy", "strategy: worktree"),
        encoding="utf-8",
    )

    loaded = load_config(repo_root)
    manager = build_workspace_manager(loaded)
    assert isinstance(manager, WorktreeWorkspaceManager)

    issue = IssueRef(id=1, title="Fix empty input crash")
    workspace = asyncio.run(manager.prepare_workspace(issue, "run-1"))

    assert (workspace / ".git").exists()
    assert (workspace / ".ai-repoagents" / "prompts" / "triage.txt.j2").exists()
    assert run_git(["rev-parse", "HEAD"], repo_root) == run_git(["rev-parse", "HEAD"], workspace)

    (workspace / "parser.py").write_text(
        "def parse_items(raw: str) -> list[str]:\n    return []\n",
        encoding="utf-8",
    )
    assert "return []" not in (repo_root / "parser.py").read_text(encoding="utf-8")

    asyncio.run(manager.cleanup_workspace(workspace))
    assert not workspace.exists()


def test_workspace_worktree_requires_git_repository(demo_repo: Path) -> None:
    config_path = demo_repo / ".ai-repoagents" / "repoagents.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("strategy: copy", "strategy: worktree"),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)
    manager = build_workspace_manager(loaded)
    issue = IssueRef(id=1, title="Fix empty input crash")

    with pytest.raises(WorkspaceError) as excinfo:
        asyncio.run(manager.prepare_workspace(issue, "run-1"))

    assert "requires the target repository to be a git work tree" in str(excinfo.value)
