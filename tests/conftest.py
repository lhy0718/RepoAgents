from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from repoagents.templates import scaffold_repository


def create_demo_repo(root: Path, issues_body: str | None = None) -> Path:
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "parser.py").write_text(
        "def parse_items(raw: str) -> list[str]:\n    return [part.strip() for part in raw.split(',')]\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Demo Repo\n", encoding="utf-8")
    (root / "tests" / "test_parser.py").write_text(
        "from parser import parse_items\n\n\ndef test_parse_items():\n    assert parse_items('a,b') == ['a', 'b']\n",
        encoding="utf-8",
    )
    issues = issues_body or """[
  {
    "id": 1,
    "number": 1,
    "title": "Fix empty input crash",
    "body": "Calling parse_items on an empty string should return an empty list.",
    "labels": ["bug"],
    "comments": []
  },
  {
    "id": 2,
    "number": 2,
    "title": "Improve README quickstart",
    "body": "Document install and test steps for contributors.",
    "labels": ["docs"],
    "comments": []
  }
]"""
    (root / "issues.json").write_text(issues, encoding="utf-8")
    scaffold_repository(
        repo_root=root,
        preset_name="python-library",
        tracker_repo="demo/repo",
        fixture_issues="issues.json",
        force=True,
    )
    config_path = root / ".ai-repoagents" / "repoagents.yaml"
    config = config_path.read_text(encoding="utf-8")
    config = config.replace("mode: codex", "mode: mock")
    config = config.replace("json: true", "json: false")
    config_path.write_text(config, encoding="utf-8")
    return root


def initialize_git_repo(root: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.name", "RepoAgents Tests"], cwd=str(root), check=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@repoagents.local"],
        cwd=str(root),
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=str(root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=str(root), check=True)
    return root


@pytest.fixture()
def demo_repo(tmp_path: Path) -> Path:
    return create_demo_repo(tmp_path / "repo")


@pytest.fixture()
def demo_git_repo(tmp_path: Path) -> Path:
    return initialize_git_repo(create_demo_repo(tmp_path / "repo"))
