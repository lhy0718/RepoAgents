from __future__ import annotations

from pathlib import Path

from reporepublic.utils import build_repo_context


def test_build_repo_context_summarizes_directories_and_tests(demo_repo: Path) -> None:
    context = build_repo_context(demo_repo)

    assert "Top-level directories:" in context
    assert "- tests/ (1 file)" in context
    assert "Root files:" in context
    assert "- README.md" in context
    assert "- parser.py" in context
    assert "Test layout:" in context
    assert "tests/test_parser.py" in context
    assert "README excerpt:" in context


def test_build_repo_context_includes_recent_git_changes_for_git_repositories(demo_git_repo: Path) -> None:
    context = build_repo_context(demo_git_repo)

    assert "Recent git changes:" in context
    assert "parser.py" in context
    assert "tests/test_parser.py" in context


def test_build_repo_context_truncates_when_requested(demo_repo: Path) -> None:
    context = build_repo_context(demo_repo, readme_chars=1200, max_chars=160)

    assert context.endswith("...[truncated]")
    assert len(context) <= 160
