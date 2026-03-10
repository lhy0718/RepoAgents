from __future__ import annotations

import json
from pathlib import Path

from repoagents.config import load_config
from repoagents.release_preview import (
    build_release_preview_exports,
    build_release_preview_snapshot,
)


def test_build_release_preview_snapshot_infers_next_patch_from_unreleased_notes(
    demo_repo: Path,
) -> None:
    _install_release_metadata(demo_repo)
    loaded = load_config(demo_repo)

    snapshot = build_release_preview_snapshot(loaded=loaded)

    assert snapshot["target"]["version"] == "0.1.1"
    assert snapshot["target"]["tag"] == "v0.1.1"
    assert snapshot["target"]["source"] == "inferred_patch_bump"
    assert snapshot["summary"]["status"] == "attention"
    assert snapshot["checks"][0]["status"] == "ok"
    assert snapshot["checks"][1]["status"] == "warn"
    assert snapshot["checks"][2]["status"] == "ok"
    assert snapshot["changelog"]["unreleased_entry_count"] == 1
    assert "pyproject.toml" in snapshot["files_to_update"]
    assert "src/repoagents/__init__.py" in snapshot["files_to_update"]
    assert snapshot["commands"]["publish"][-1].startswith("gh release create v0.1.1")


def test_build_release_preview_snapshot_blocks_existing_target_version(
    demo_repo: Path,
) -> None:
    _install_release_metadata(demo_repo)
    loaded = load_config(demo_repo)

    snapshot = build_release_preview_snapshot(loaded=loaded, target_version="0.1.0")

    assert snapshot["summary"]["status"] == "issues"
    assert snapshot["target"]["tag"] == "v0.1.0"
    assert snapshot["checks"][1]["status"] == "error"
    assert "already contains a released section" in snapshot["checks"][1]["message"]


def test_build_release_preview_exports_write_preview_and_notes_files(
    demo_repo: Path,
) -> None:
    _install_release_metadata(demo_repo)
    loaded = load_config(demo_repo)
    snapshot = build_release_preview_snapshot(loaded=loaded)

    result = build_release_preview_exports(
        snapshot=snapshot,
        output_path=demo_repo / ".ai-repoagents" / "reports" / "release-preview.json",
        formats=("json", "markdown"),
    )

    json_payload = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
    markdown = result.output_paths["markdown"].read_text(encoding="utf-8")
    notes_markdown = result.notes_markdown_path.read_text(encoding="utf-8")

    assert result.output_paths["json"].exists()
    assert result.output_paths["markdown"].exists()
    assert result.notes_markdown_path.name == "release-notes-v0.1.1.md"
    assert json_payload["artifacts"]["notes_markdown_path"] == str(result.notes_markdown_path)
    assert "# Release preview" in markdown
    assert "## GitHub release body" in markdown
    assert "## Highlights" in notes_markdown
    assert "publish-enabled sandbox rollout example" in notes_markdown


def _install_release_metadata(repo_root: Path) -> None:
    (repo_root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "repoagents"',
                'version = "0.1.0"',
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
                "",
                "## [0.1.0] - 2026-03-09",
                "",
                "### Added",
                "",
                "- initial public-preview release of RepoAgents",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
