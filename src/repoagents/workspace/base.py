from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from repoagents.models import IssueRef


class WorkspaceError(RuntimeError):
    """Raised when RepoAgents cannot prepare or clean up a workspace."""


class WorkspaceManager(ABC):
    @abstractmethod
    async def prepare_workspace(self, issue: IssueRef, run_id: str) -> Path:
        raise NotImplementedError

    async def cleanup_workspace(self, workspace_path: Path) -> None:
        del workspace_path
