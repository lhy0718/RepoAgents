from __future__ import annotations

import json
from pathlib import Path

import pytest

import repoagents.release_assets as release_assets
from repoagents.release_assets import (
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
        output_path=tmp_path / ".ai-repoagents" / "reports" / "release-assets.json",
        formats=("json", "markdown"),
    )

    payload = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
    summary = result.asset_summary_path.read_text(encoding="utf-8")
    assert result.output_paths["markdown"].exists()
    assert result.asset_summary_path.name == "release-assets-v0.1.1.md"
    assert payload["artifact_outputs"]["asset_summary_path"] == str(result.asset_summary_path)
    assert "# Release asset dry-run for v0.1.1" in summary


def test_build_release_asset_snapshot_prefers_target_version_artifacts_for_smoke_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_release_metadata(tmp_path, version="0.1.1")
    _install_fake_dist(tmp_path, version="0.1.0")
    _install_fake_dist(tmp_path, version="0.1.1")

    captured: dict[str, str] = {}

    def _fake_smoke_install(*, repo_root: Path, dist_dir: Path, wheel_path: Path | None) -> dict[str, object]:
        captured["wheel_path"] = str(wheel_path) if wheel_path is not None else ""
        return {
            "ran": True,
            "status": "ok",
            "command": f"install {wheel_path}",
            "return_code": 0,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr(release_assets, "_run_smoke_install", _fake_smoke_install)

    snapshot = build_release_asset_snapshot(
        repo_root=tmp_path,
        smoke_install=True,
    )

    assert snapshot["summary"]["status"] == "clean"
    assert snapshot["summary"]["target_wheel_count"] == 1
    assert snapshot["summary"]["target_sdist_count"] == 1
    assert captured["wheel_path"].endswith("repoagents-0.1.1-py3-none-any.whl")
    assert "repoagents-0.1.1-py3-none-any.whl" in snapshot["smoke_install"]["command"]


def _install_release_metadata(repo_root: Path, *, version: str) -> None:
    (repo_root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "repoagents"',
                f'version = "{version}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    package_init = repo_root / "src" / "repoagents" / "__init__.py"
    package_init.parent.mkdir(parents=True, exist_ok=True)
    package_init.write_text(
        '\n'.join(
            [
                '"""RepoAgents package."""',
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
    (dist_dir / f"repoagents-{version}-py3-none-any.whl").write_text(
        "fake wheel payload\n",
        encoding="utf-8",
    )
    (dist_dir / f"repoagents-{version}.tar.gz").write_text(
        "fake sdist payload\n",
        encoding="utf-8",
    )
