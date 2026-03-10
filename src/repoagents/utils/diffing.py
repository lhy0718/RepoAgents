from __future__ import annotations

from difflib import unified_diff
from pathlib import Path

from repoagents.models import DiffReport


IGNORED_PREFIXES = {
    ".ai-repoagents/workspaces",
    ".ai-repoagents/state",
    ".ai-repoagents/artifacts",
    ".git",
}


def build_diff_report(source_root: Path, workspace_root: Path) -> DiffReport:
    source_files = _collect_files(source_root)
    workspace_files = _collect_files(workspace_root)

    changed_files: list[str] = []
    added_files: list[str] = []
    removed_files: list[str] = []
    total_added = 0
    total_removed = 0
    diff_parts: list[str] = []

    for rel_path in sorted(set(source_files) | set(workspace_files)):
        source_path = source_files.get(rel_path)
        workspace_path = workspace_files.get(rel_path)

        if source_path and not workspace_path:
            removed_files.append(rel_path)
            source_lines = source_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            total_removed += len(source_lines)
            diff_parts.extend(
                unified_diff(source_lines, [], fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}", lineterm="")
            )
            continue
        if workspace_path and not source_path:
            added_files.append(rel_path)
            workspace_lines = workspace_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            total_added += len(workspace_lines)
            diff_parts.extend(
                unified_diff([], workspace_lines, fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}", lineterm="")
            )
            continue
        if not source_path or not workspace_path:
            continue
        source_lines = source_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        workspace_lines = workspace_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if source_lines == workspace_lines:
            continue
        changed_files.append(rel_path)
        total_added += sum(1 for line in workspace_lines if line not in source_lines)
        total_removed += sum(1 for line in source_lines if line not in workspace_lines)
        diff_parts.extend(
            unified_diff(
                source_lines,
                workspace_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
                lineterm="",
            )
        )

    summary = (
        f"changed={len(changed_files)} added={len(added_files)} "
        f"removed={len(removed_files)} +{total_added}/-{total_removed}"
    )
    return DiffReport(
        changed_files=changed_files,
        added_files=added_files,
        removed_files=removed_files,
        total_added_lines=total_added,
        total_removed_lines=total_removed,
        unified_diff="\n".join(diff_parts)[:20000],
        summary=summary,
    )


def _collect_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel == prefix or rel.startswith(f"{prefix}/") for prefix in IGNORED_PREFIXES):
            continue
        files[rel] = path
    return files
