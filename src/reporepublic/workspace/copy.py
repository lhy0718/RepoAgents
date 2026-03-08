from __future__ import annotations

import shutil
from pathlib import Path

from reporepublic.models import IssueRef
from reporepublic.utils.files import ensure_dir
from reporepublic.workspace.base import WorkspaceManager


class CopyWorkspaceManager(WorkspaceManager):
    def __init__(self, repo_root: Path, workspace_root: Path) -> None:
        self.repo_root = repo_root
        self.workspace_root = workspace_root

    async def prepare_workspace(self, issue: IssueRef, run_id: str) -> Path:
        issue_root = ensure_dir(self.workspace_root / f"issue-{issue.id}" / run_id)
        workspace_path = issue_root / "repo"
        shutil.copytree(
            self.repo_root,
            workspace_path,
            ignore=self._ignore,
            dirs_exist_ok=False,
        )
        return workspace_path

    def _ignore(self, current_dir: str, names: list[str]) -> set[str]:
        path = Path(current_dir)
        rel = path.relative_to(self.repo_root).as_posix() if path != self.repo_root else "."
        ignored: set[str] = set()
        if rel == ".":
            ignored.update({".git", ".venv", ".pytest_cache", "__pycache__"})
        if rel == ".ai-republic":
            ignored.update({"workspaces", "state", "artifacts"})
        if rel.endswith("__pycache__"):
            ignored.update(names)
        return ignored

    async def cleanup_workspace(self, workspace_path: Path) -> None:
        if not workspace_path.exists():
            return
        run_root = workspace_path.parent
        if run_root.exists():
            shutil.rmtree(run_root)
        self._prune_empty_parents(run_root.parent)

    def _prune_empty_parents(self, path: Path) -> None:
        current = path
        workspace_root = self.workspace_root.resolve()
        while current.exists() and current.resolve() != workspace_root:
            if any(current.iterdir()):
                break
            current.rmdir()
            current = current.parent
