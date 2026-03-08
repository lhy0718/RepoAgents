from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


IGNORED_RUNTIME_PREFIXES = {
    ".git",
    ".ai-republic/artifacts",
    ".ai-republic/workspaces",
    ".ai-republic/state",
    ".ai-republic/branches",
    ".ai-republic/logs",
}


class GitCommandError(RuntimeError):
    """Raised when a git command fails."""


def run_git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        raise GitCommandError(
            f"git {' '.join(args)} failed in {cwd}: {stderr or stdout or 'unknown git error'}"
        )
    return completed.stdout.rstrip()


def is_git_repository(path: Path) -> bool:
    try:
        run_git(["rev-parse", "--is-inside-work-tree"], path)
    except GitCommandError:
        return False
    return True


def list_dirty_working_tree_entries(path: Path) -> list[str]:
    if not is_git_repository(path):
        return []
    args = ["status", "--porcelain", "--untracked-files=all", "--", "."]
    args.extend(
        f":(exclude){prefix}"
        for prefix in sorted(IGNORED_RUNTIME_PREFIXES)
        if prefix != ".git"
    )
    output = run_git(args, path)
    if not output:
        return []
    entries: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        status = line[:2].strip() or "?"
        target = line[3:].strip() if len(line) > 3 else line.strip()
        entries.append(f"{status} {target}".strip())
    return entries


def has_dirty_working_tree(path: Path) -> bool:
    return bool(list_dirty_working_tree_entries(path))


def sanitize_branch_name(raw: str, issue_id: int | None = None) -> str:
    candidate = raw.strip().lower().replace("_", "-")
    candidate = re.sub(r"[^a-z0-9/.-]+", "-", candidate)
    candidate = re.sub(r"-{2,}", "-", candidate)
    candidate = candidate.strip("-. /")
    while "//" in candidate:
        candidate = candidate.replace("//", "/")
    if not candidate:
        candidate = f"reporepublic/issue-{issue_id}" if issue_id is not None else "reporepublic/update"
    if candidate.endswith(".lock"):
        candidate = f"{candidate}-branch"
    if not candidate.startswith("reporepublic/"):
        candidate = f"reporepublic/{candidate}"
    return candidate[:96].rstrip("/.")


def sync_workspace_to_git_clone(workspace_root: Path, git_clone_root: Path) -> None:
    source_files = _collect_files(workspace_root)
    destination_files = _collect_files(git_clone_root)

    for rel_path in sorted(set(destination_files) - set(source_files), reverse=True):
        destination = git_clone_root / rel_path
        if destination.exists():
            destination.unlink()

    for rel_path, source in source_files.items():
        destination = git_clone_root / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    _prune_empty_directories(git_clone_root)


def _collect_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(root).as_posix()
        if _is_ignored(rel_path):
            continue
        files[rel_path] = path
    return files


def _prune_empty_directories(root: Path) -> None:
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for directory in directories:
        rel_path = directory.relative_to(root).as_posix()
        if _is_ignored(rel_path):
            continue
        if any(directory.iterdir()):
            continue
        directory.rmdir()


def _is_ignored(rel_path: str) -> bool:
    return any(
        rel_path == prefix or rel_path.startswith(f"{prefix}/")
        for prefix in IGNORED_RUNTIME_PREFIXES
    )
