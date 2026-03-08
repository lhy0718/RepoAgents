from __future__ import annotations

from pathlib import Path

from reporepublic.utils import has_dirty_working_tree, list_dirty_working_tree_entries


def test_dirty_working_tree_ignores_reporepublic_runtime_paths(demo_git_repo: Path) -> None:
    runtime_state = demo_git_repo / ".ai-republic" / "state" / "runs.json"
    runtime_state.write_text('{\n  "runs": {"1": "dirty"}\n}\n', encoding="utf-8")
    (demo_git_repo / "parser.py").write_text(
        "def parse_items(raw: str) -> list[str]:\n    return []\n",
        encoding="utf-8",
    )

    entries = list_dirty_working_tree_entries(demo_git_repo)

    assert has_dirty_working_tree(demo_git_repo) is True
    assert any(entry.endswith("parser.py") for entry in entries)
    assert not any("runs.json" in entry for entry in entries)
