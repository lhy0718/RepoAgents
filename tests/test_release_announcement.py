from __future__ import annotations

import json
from pathlib import Path

from reporepublic.config import load_config
from reporepublic.release_announcement import (
    build_release_announcement_exports,
    build_release_announcement_snapshot,
)


def test_build_release_announcement_snapshot_produces_copy_pack(
    demo_repo: Path,
) -> None:
    _install_release_metadata(demo_repo)
    loaded = load_config(demo_repo)

    snapshot = build_release_announcement_snapshot(loaded=loaded)

    assert snapshot["target"]["version"] == "0.1.1"
    assert snapshot["summary"]["status"] == "attention"
    assert snapshot["summary"]["snippet_count"] == 5
    assert snapshot["highlights"][0].startswith("publish-enabled sandbox rollout example")
    assert "# RepoRepublic v0.1.1" in snapshot["copy_pack"]["announcement"]
    assert "# RepoRepublic v0.1.1 public preview" in snapshot["copy_pack"]["discussion"]
    assert "RepoRepublic v0.1.1 is out in public preview." in snapshot["copy_pack"]["social"]
    assert "# Release cut checklist for v0.1.1" in snapshot["copy_pack"]["release_cut"]


def test_build_release_announcement_exports_write_snippet_files(
    demo_repo: Path,
) -> None:
    _install_release_metadata(demo_repo)
    loaded = load_config(demo_repo)
    snapshot = build_release_announcement_snapshot(loaded=loaded)

    result = build_release_announcement_exports(
        snapshot=snapshot,
        output_path=demo_repo / ".ai-republic" / "reports" / "release-announce.json",
        formats=("json", "markdown"),
    )

    payload = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
    assert result.output_paths["markdown"].exists()
    assert result.snippet_paths["announcement"].name == "announcement-v0.1.1.md"
    assert result.snippet_paths["discussion"].exists()
    assert result.snippet_paths["social"].exists()
    assert result.snippet_paths["release_cut"].exists()
    assert result.snippet_paths["release_notes"].exists()
    assert payload["artifacts"]["snippet_paths"]["announcement"] == str(result.snippet_paths["announcement"])


def _install_release_metadata(repo_root: Path) -> None:
    (repo_root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "reporepublic"',
                'version = "0.1.0"',
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
                '__version__ = "0.1.0"',
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
                "- publish-enabled sandbox rollout example with staged `github smoke` gates and handoff bundle rehearsal",
                "- release preview and operator handoff exports for maintainers",
                "",
                "## [0.1.0] - 2026-03-09",
                "",
                "### Added",
                "",
                "- initial public-preview release of RepoRepublic",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
