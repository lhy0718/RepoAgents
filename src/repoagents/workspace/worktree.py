from __future__ import annotations

from pathlib import Path

from repoagents.models import IssueRef
from repoagents.utils import GitCommandError, ensure_dir, is_git_repository, run_git
from repoagents.workspace.base import WorkspaceError, WorkspaceManager


class WorktreeWorkspaceManager(WorkspaceManager):
    def __init__(self, repo_root: Path, workspace_root: Path) -> None:
        self.repo_root = repo_root
        self.workspace_root = workspace_root

    async def prepare_workspace(self, issue: IssueRef, run_id: str) -> Path:
        if not is_git_repository(self.repo_root):
            raise WorkspaceError(
                "workspace.strategy=worktree requires the target repository to be a git work tree."
            )
        issue_root = ensure_dir(self.workspace_root / f"issue-{issue.id}" / run_id)
        workspace_path = issue_root / "repo"
        try:
            run_git(
                ["worktree", "add", "--detach", str(workspace_path), "HEAD"],
                cwd=self.repo_root,
            )
        except GitCommandError as exc:
            raise WorkspaceError(
                f"Could not prepare git worktree at {workspace_path}: {exc}"
            ) from exc
        return workspace_path

    async def cleanup_workspace(self, workspace_path: Path) -> None:
        if not is_git_repository(self.repo_root):
            raise WorkspaceError(
                "workspace.strategy=worktree cleanup requires the target repository to be a git work tree."
            )
        if not workspace_path.exists():
            return
        try:
            run_git(["worktree", "remove", "--force", str(workspace_path)], cwd=self.repo_root)
            run_git(["worktree", "prune"], cwd=self.repo_root)
        except GitCommandError as exc:
            raise WorkspaceError(
                f"Could not clean up git worktree at {workspace_path}: {exc}"
            ) from exc
        self._prune_empty_parents(workspace_path.parent)

    def _prune_empty_parents(self, path: Path) -> None:
        current = path
        workspace_root = self.workspace_root.resolve()
        while current.exists() and current.resolve() != workspace_root:
            if any(current.iterdir()):
                break
            current.rmdir()
            current = current.parent
