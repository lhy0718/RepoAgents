from __future__ import annotations

import json
from pathlib import Path

from reporepublic.release_assets import (
    build_release_asset_exports,
    build_release_asset_snapshot,
)


def test_build_release_asset_snapshot_reads_dist_artifacts_without_config(tmp_path: Path) -> None:
    _install_release_metadata(tmp_path, version="0.1.1")
    _install_fake_dist(tmp_path, version="0.1.1")

    snapshot = build_release_asset_snapshot(repo_root=tmp_path)

    assert snapshot["summary"]["status"] == "clean"
    assert snapshot["summary"]["artifact_count"] == 2
    assert snapshot["summary"]["wheel_count"] == 1
    assert snapshot["summary"]["sdist_count"] == 1
    assert snapshot["artifacts"][0]["sha256"]
    assert snapshot["artifacts"][1]["version_matches_target"] is True


def test_build_release_asset_exports_write_report_and_summary(tmp_path: Path) -> None:
    _install_release_metadata(tmp_path, version="0.1.1")
    _install_fake_dist(tmp_path, version="0.1.1")
    snapshot = build_release_asset_snapshot(repo_root=tmp_path)

    result = build_release_asset_exports(
        snapshot=snapshot,
        output_path=tmp_path / ".ai-republic" / "reports" / "release-assets.json",
        formats=("json", "markdown"),
    )

    payload = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
    summary = result.asset_summary_path.read_text(encoding="utf-8")
    assert result.output_paths["markdown"].exists()
    assert result.asset_summary_path.name == "release-assets-v0.1.1.md"
    assert payload["artifact_outputs"]["asset_summary_path"] == str(result.asset_summary_path)
    assert "# Release asset dry-run for v0.1.1" in summary


def _install_release_metadata(repo_root: Path, *, version: str) -> None:
    (repo_root / "pyproject.toml").write_text(
        "\n".join(
            [
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
                "- release preview and release asset dry-run surfaces",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _install_fake_dist(repo_root: Path, *, version: str) -> None:
    dist_dir = repo_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / f"reporepublic-{version}-py3-none-any.whl").write_text(
        "fake wheel payload\n",
        encoding="utf-8",
    )
    (dist_dir / f"reporepublic-{version}.tar.gz").write_text(
        "fake sdist payload\n",
        encoding="utf-8",
    )
