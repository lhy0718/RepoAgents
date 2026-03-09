from __future__ import annotations

import json
import subprocess
from pathlib import Path

from reporepublic.release_checklist import (
    build_release_checklist_exports,
    build_release_checklist_snapshot,
)


def test_build_release_checklist_snapshot_is_clean_for_ready_repo(tmp_path: Path) -> None:
    _install_release_repo(tmp_path, version="0.1.1")
    _install_release_hygiene(tmp_path)
    _install_fake_dist(tmp_path, version="0.1.1")
    _initialize_git_repo(tmp_path)

    snapshot = build_release_checklist_snapshot(
        repo_root=tmp_path,
        run_tests=True,
        build=False,
        smoke_install=False,
        test_command=("bash", "-lc", "printf release-tests-ok"),
    )

    assert snapshot["summary"]["status"] == "clean"
    assert snapshot["summary"]["ready_to_publish"] is True
    assert snapshot["announcement"]["snippet_count"] == 5
    assert snapshot["oss_hygiene"]["status"] == "ok"
    assert snapshot["tests"]["status"] == "ok"
    assert any(item["name"] == "Release assets" and item["status"] == "ok" for item in snapshot["checklist"])


def test_build_release_checklist_snapshot_blocks_missing_governance_files(tmp_path: Path) -> None:
    _install_release_repo(tmp_path, version="0.1.1")
    _install_fake_dist(tmp_path, version="0.1.1")
    _initialize_git_repo(tmp_path)

    snapshot = build_release_checklist_snapshot(
        repo_root=tmp_path,
        run_tests=False,
        build=False,
        smoke_install=False,
    )

    assert snapshot["summary"]["status"] == "issues"
    assert snapshot["oss_hygiene"]["status"] == "error"
    assert any(
        item["name"] == "Open-source release files" and item["status"] == "error"
        for item in snapshot["checklist"]
    )


def test_build_release_checklist_exports_write_report_and_companion_artifacts(tmp_path: Path) -> None:
    _install_release_repo(tmp_path, version="0.1.1")
    _install_release_hygiene(tmp_path)
    _install_fake_dist(tmp_path, version="0.1.1")
    _initialize_git_repo(tmp_path)
    snapshot = build_release_checklist_snapshot(
        repo_root=tmp_path,
        run_tests=True,
        build=False,
        smoke_install=False,
        test_command=("bash", "-lc", "printf release-tests-ok"),
    )

    result = build_release_checklist_exports(
        snapshot=snapshot,
        output_path=tmp_path / ".ai-republic" / "reports" / "release-checklist.json",
        formats=("json", "markdown"),
    )

    payload = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
    markdown = result.output_paths["markdown"].read_text(encoding="utf-8")

    assert result.output_paths["markdown"].exists()
    assert payload["artifacts"]["preview"]["notes_markdown_path"].endswith("release-notes-v0.1.1.md")
    assert payload["artifacts"]["announcement"]["snippet_paths"]["release_cut"].endswith(
        "release-cut-v0.1.1.md"
    )
    assert payload["artifacts"]["assets"]["asset_summary_path"].endswith("release-assets-v0.1.1.md")
    assert "# Release preflight checklist" in markdown
    assert "## One-command preflight" in markdown


def _install_release_repo(repo_root: Path, *, version: str) -> None:
    (repo_root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[build-system]",
                'requires = ["setuptools>=68", "wheel"]',
                'build-backend = "setuptools.build_meta"',
                "",
                "[project]",
                'name = "reporepublic"',
                f'version = "{version}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    package_init = repo_root / "src" / "reporepublic" / "__init__.py"
    package_init.parent.mkdir(parents=True, exist_ok=True)
    package_init.write_text(
        '\n'.join(
            [
                '"""RepoRepublic package."""',
                "",
                '__all__ = ["__version__"]',
                "",
                f'__version__ = "{version}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "CHANGELOG.md").write_text(
        "\n".join(
            [
                "# Changelog",
                "",
                "## [Unreleased]",
                "",
                "### Added",
                "",
                "- release preflight checklist surface that combines preview, assets, and OSS readiness",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _install_release_hygiene(repo_root: Path) -> None:
    for relative_path, body in (
        ("LICENSE", "MIT License\n"),
        ("CONTRIBUTING.md", "# Contributing\n"),
        ("SECURITY.md", "# Security\n"),
        ("CODE_OF_CONDUCT.md", "# Code of Conduct\n"),
        ("README.md", "# RepoRepublic\n"),
        ("QUICKSTART.md", "# Quickstart\n"),
        ("docs/release.md", "# Release Checklist\n"),
        (".github/workflows/ci.yml", "name: ci\n"),
    ):
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def _install_fake_dist(repo_root: Path, *, version: str) -> None:
    dist_dir = repo_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / f"reporepublic-{version}-py3-none-any.whl").write_text("fake wheel\n", encoding="utf-8")
    (dist_dir / f"reporepublic-{version}.tar.gz").write_text("fake sdist\n", encoding="utf-8")


def _initialize_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "RepoRepublic Tests"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@reporepublic.local"],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo_root, check=True)
