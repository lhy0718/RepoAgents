from __future__ import annotations

from reporepublic.config import LoadedConfig
from reporepublic.workspace.base import WorkspaceManager
from reporepublic.workspace.copy import CopyWorkspaceManager
from reporepublic.workspace.worktree import WorktreeWorkspaceManager


def build_workspace_manager(loaded: LoadedConfig) -> WorkspaceManager:
    strategy = loaded.data.workspace.strategy
    if strategy == "copy":
        return CopyWorkspaceManager(loaded.repo_root, loaded.workspace_root)
    if strategy == "worktree":
        return WorktreeWorkspaceManager(loaded.repo_root, loaded.workspace_root)
    raise ValueError(f"Unsupported workspace strategy: {strategy}")
