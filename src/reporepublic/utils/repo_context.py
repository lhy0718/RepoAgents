from __future__ import annotations

from collections import Counter
from pathlib import Path

from reporepublic.utils.git import GitCommandError, is_git_repository, run_git


IGNORED_PREFIXES = (
    ".git",
    ".ai-republic/artifacts",
    ".ai-republic/workspaces",
    ".ai-republic/state",
    ".ai-republic/branches",
    ".ai-republic/logs",
)
README_CANDIDATES = ("README.md", "README.rst", "README.txt")
TEST_DIRECTORY_MARKERS = ("tests/", "test/", "__tests__/", "spec/")
TEST_FILE_MARKERS = ("test_", "_test.", ".spec.", ".test.")


def build_repo_context(
    repo_root: Path,
    max_files: int = 40,
    readme_chars: int = 1200,
    max_directories: int = 8,
    max_recent_files: int = 8,
    max_chars: int = 4000,
) -> str:
    files = _collect_repo_files(repo_root)
    top_level_directories = _summarize_top_level_directories(files, max_directories=max_directories)
    root_files = [path for path in files if "/" not in path][:max_directories]
    test_files = _collect_test_files(files)
    recent_git_changes = _collect_recent_git_changes(repo_root, max_recent_files=max_recent_files)
    readme_excerpt = _load_readme_excerpt(repo_root, readme_chars=readme_chars)

    lines = ["Repository context:"]

    if top_level_directories:
        lines.extend(["", "Top-level directories:", *top_level_directories])

    if root_files:
        lines.extend(["", "Root files:", *[f"- {file_path}" for file_path in root_files]])

    lines.extend(["", "Test layout:"])
    if test_files:
        test_directories = sorted(
            {file_path.rsplit("/", 1)[0] + "/" for file_path in test_files if "/" in file_path}
        )
        if test_directories:
            lines.append(f"- directories: {', '.join(test_directories)}")
        lines.extend(f"- {file_path}" for file_path in test_files[:max_files])
    else:
        lines.append("- no obvious tests detected")

    if recent_git_changes:
        lines.extend(["", "Recent git changes:", *[f"- {file_path}" for file_path in recent_git_changes]])

    lines.extend(["", "File sample:", *[f"- {file_path}" for file_path in files[:max_files]]])
    if readme_excerpt:
        lines.extend(["", "README excerpt:", readme_excerpt])

    context = "\n".join(lines)
    if len(context) <= max_chars:
        return context
    trimmed = context[: max_chars - len("\n...[truncated]")].rstrip()
    return f"{trimmed}\n...[truncated]"


def _collect_repo_files(repo_root: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(repo_root).as_posix()
        if _is_ignored(rel_path):
            continue
        files.append(rel_path)
    return files


def _summarize_top_level_directories(files: list[str], max_directories: int) -> list[str]:
    counter: Counter[str] = Counter()
    for file_path in files:
        if "/" not in file_path:
            continue
        top_level_directory = file_path.split("/", 1)[0]
        counter[top_level_directory] += 1
    entries = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    summary: list[str] = []
    for directory, file_count in entries[:max_directories]:
        label = "file" if file_count == 1 else "files"
        summary.append(f"- {directory}/ ({file_count} {label})")
    return summary


def _collect_test_files(files: list[str]) -> list[str]:
    return [
        file_path
        for file_path in files
        if file_path.startswith(TEST_DIRECTORY_MARKERS) or _looks_like_test_file(file_path)
    ]


def _looks_like_test_file(file_path: str) -> bool:
    name = file_path.rsplit("/", 1)[-1].lower()
    return any(name.startswith(marker) or marker in name for marker in TEST_FILE_MARKERS)


def _collect_recent_git_changes(repo_root: Path, max_recent_files: int) -> list[str]:
    if not is_git_repository(repo_root):
        return []
    try:
        output = run_git(["log", "--name-only", "--pretty=format:", "-n", "5", "--", "."], repo_root)
    except GitCommandError:
        return []

    recent_files: list[str] = []
    for line in output.splitlines():
        rel_path = line.strip()
        if not rel_path or _is_ignored(rel_path) or rel_path in recent_files:
            continue
        recent_files.append(rel_path)
        if len(recent_files) >= max_recent_files:
            break
    return recent_files


def _load_readme_excerpt(repo_root: Path, readme_chars: int) -> str:
    for candidate in README_CANDIDATES:
        target = repo_root / candidate
        if target.exists():
            return target.read_text(encoding="utf-8", errors="ignore")[:readme_chars]
    return ""


def _is_ignored(rel_path: str) -> bool:
    return any(
        rel_path == prefix or rel_path.startswith(f"{prefix}/")
        for prefix in IGNORED_PREFIXES
    )
