from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from reporepublic.config import LoadedConfig
from reporepublic.release_announcement import (
    build_release_announcement_exports,
    build_release_announcement_snapshot,
)
from reporepublic.release_assets import build_release_asset_exports, build_release_asset_snapshot
from reporepublic.release_preview import build_release_preview_exports, build_release_preview_snapshot
from reporepublic.utils.files import write_text_file


VALID_RELEASE_CHECKLIST_FORMATS = ("json", "markdown")
DEFAULT_RELEASE_TEST_COMMAND = ("uv", "run", "pytest", "-q")
OSS_RELEASE_REQUIRED_FILES = (
    ("LICENSE", "License file"),
    ("CONTRIBUTING.md", "Contributing guide"),
    ("SECURITY.md", "Security policy"),
    ("CODE_OF_CONDUCT.md", "Code of conduct"),
    ("README.md", "README"),
    ("QUICKSTART.md", "Quickstart"),
    ("docs/release.md", "Release guide"),
    (".github/workflows/ci.yml", "CI workflow"),
)


@dataclass(frozen=True, slots=True)
class ReleaseChecklistBuildResult:
    output_paths: dict[str, Path]
    snapshot: dict[str, Any]


def normalize_release_checklist_formats(
    formats: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if not formats:
        return ("json",)
    normalized: list[str] = []
    for value in formats:
        lowered = value.strip().lower()
        if not lowered:
            continue
        if lowered == "all":
            for item in VALID_RELEASE_CHECKLIST_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_RELEASE_CHECKLIST_FORMATS:
            raise ValueError(
                "Unsupported release checklist format. Expected one of: json, markdown, all"
            )
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def resolve_release_checklist_export_paths(
    target: Path,
    formats: tuple[str, ...],
) -> dict[str, Path]:
    resolved = target.resolve()
    export_paths: dict[str, Path] = {}
    for export_format in formats:
        suffix = ".md" if export_format == "markdown" else ".json"
        export_paths[export_format] = resolved.with_suffix(suffix)
    return export_paths


def build_release_checklist_snapshot(
    *,
    loaded: LoadedConfig | None = None,
    repo_root: Path | None = None,
    target_version: str | None = None,
    target_tag: str | None = None,
    run_tests: bool = True,
    build: bool = True,
    smoke_install: bool = True,
    test_command: Sequence[str] | None = None,
) -> dict[str, Any]:
    preview_snapshot = build_release_preview_snapshot(
        loaded=loaded,
        repo_root=repo_root,
        target_version=target_version,
        target_tag=target_tag,
    )
    announcement_snapshot = build_release_announcement_snapshot(
        loaded=loaded,
        repo_root=repo_root,
        target_version=str(preview_snapshot["target"]["version"]),
        target_tag=str(preview_snapshot["target"]["tag"]),
    )
    assets_snapshot = build_release_asset_snapshot(
        loaded=loaded,
        repo_root=repo_root,
        target_version=str(preview_snapshot["target"]["version"]),
        target_tag=str(preview_snapshot["target"]["tag"]),
        build=build,
        smoke_install=smoke_install,
    )
    resolved_repo_root = Path(preview_snapshot["meta"]["repo_root"]).resolve()
    oss_hygiene = _build_oss_hygiene_snapshot(resolved_repo_root)
    tests = _run_release_tests(
        repo_root=resolved_repo_root,
        run_tests=run_tests,
        test_command=test_command,
    )

    checklist = _build_release_checklist_items(
        preview_snapshot=preview_snapshot,
        announcement_snapshot=announcement_snapshot,
        assets_snapshot=assets_snapshot,
        oss_hygiene=oss_hygiene,
        tests=tests,
    )
    summary = _build_release_checklist_summary(
        checklist=checklist,
        target_tag=str(preview_snapshot["target"]["tag"]),
    )
    return {
        "meta": {
            "kind": "release_checklist",
            "repo_root": str(resolved_repo_root),
            "rendered_at": preview_snapshot["meta"]["rendered_at"],
        },
        "summary": summary,
        "target": preview_snapshot["target"],
        "preview": {
            "status": preview_snapshot["summary"]["status"],
            "message": preview_snapshot["summary"]["message"],
            "warning_count": preview_snapshot["summary"]["warning_count"],
            "error_count": preview_snapshot["summary"]["error_count"],
        },
        "announcement": {
            "status": announcement_snapshot["summary"]["status"],
            "message": announcement_snapshot["summary"]["message"],
            "snippet_count": announcement_snapshot["summary"]["snippet_count"],
        },
        "assets": {
            "status": assets_snapshot["summary"]["status"],
            "message": assets_snapshot["summary"]["message"],
            "artifact_count": assets_snapshot["summary"]["artifact_count"],
            "build_status": assets_snapshot["build"]["status"],
            "smoke_install_status": assets_snapshot["smoke_install"]["status"],
            "warning_count": assets_snapshot["summary"]["warning_count"],
            "error_count": assets_snapshot["summary"]["error_count"],
        },
        "tests": tests,
        "oss_hygiene": oss_hygiene,
        "checklist": checklist,
        "commands": {
            "run": [
                "uv run republic release check --format all",
                "bash scripts/release_preflight.sh",
            ],
            "publish": list(preview_snapshot["commands"]["publish"]),
        },
        "_preview_snapshot": preview_snapshot,
        "_announcement_snapshot": announcement_snapshot,
        "_assets_snapshot": assets_snapshot,
    }


def build_release_checklist_exports(
    *,
    snapshot: dict[str, Any],
    output_path: Path,
    formats: tuple[str, ...],
) -> ReleaseChecklistBuildResult:
    export_paths = resolve_release_checklist_export_paths(output_path, formats)
    export_root = output_path.resolve().parent
    preview_result = build_release_preview_exports(
        snapshot=_mapping(snapshot, "_preview_snapshot"),
        output_path=export_root / "release-preview.json",
        formats=formats,
    )
    announcement_result = build_release_announcement_exports(
        snapshot=_mapping(snapshot, "_announcement_snapshot"),
        output_path=export_root / "release-announce.json",
        formats=formats,
    )
    assets_result = build_release_asset_exports(
        snapshot=_mapping(snapshot, "_assets_snapshot"),
        output_path=export_root / "release-assets.json",
        formats=formats,
    )

    materialized_snapshot = _public_release_checklist_snapshot(snapshot)
    materialized_snapshot["artifacts"] = {
        "json_path": str(export_paths["json"]) if "json" in export_paths else None,
        "markdown_path": str(export_paths["markdown"]) if "markdown" in export_paths else None,
        "preview": {
            "output_paths": {key: str(path) for key, path in preview_result.output_paths.items()},
            "notes_markdown_path": str(preview_result.notes_markdown_path),
        },
        "announcement": {
            "output_paths": {key: str(path) for key, path in announcement_result.output_paths.items()},
            "snippet_paths": {key: str(path) for key, path in announcement_result.snippet_paths.items()},
        },
        "assets": {
            "output_paths": {key: str(path) for key, path in assets_result.output_paths.items()},
            "asset_summary_path": str(assets_result.asset_summary_path),
        },
    }

    if "json" in export_paths:
        write_text_file(export_paths["json"], render_release_checklist_json(materialized_snapshot))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_release_checklist_markdown(materialized_snapshot))
    return ReleaseChecklistBuildResult(
        output_paths=export_paths,
        snapshot=materialized_snapshot,
    )


def render_release_checklist_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True)


def render_release_checklist_markdown(snapshot: dict[str, Any]) -> str:
    meta = _mapping(snapshot, "meta")
    summary = _mapping(snapshot, "summary")
    target = _mapping(snapshot, "target")
    preview = _mapping(snapshot, "preview")
    announcement = _mapping(snapshot, "announcement")
    assets = _mapping(snapshot, "assets")
    tests = _mapping(snapshot, "tests")
    oss_hygiene = _mapping(snapshot, "oss_hygiene")
    artifacts = _mapping(snapshot, "artifacts")
    commands = _mapping(snapshot, "commands")

    lines = [
        "# Release preflight checklist",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- status: {summary.get('status', '-')}",
        f"- ready_to_publish: {summary.get('ready_to_publish', False)}",
        f"- message: {summary.get('message', '-')}",
        "",
        "## Target",
        f"- version: {target.get('version', '-')}",
        f"- tag: {target.get('tag', '-')}",
        f"- title: {target.get('title', '-')}",
        "",
        "## One-command preflight",
    ]
    for command in _list(commands.get("run")):
        lines.append(f"- `{command}`")
    lines.extend(
        [
            "",
            "## Checklist",
        ]
    )
    for item in _list(snapshot.get("checklist")):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "-")
        marker = "x" if status == "ok" else " "
        lines.append(
            f"- [{marker}] {item.get('name', 'Unnamed check')} ({status}): {item.get('message', '-')}"
        )
        hint = item.get("hint")
        if isinstance(hint, str) and hint:
            lines.append(f"  - hint: {hint}")
        for detail_line in _list(item.get("detail_lines")):
            lines.append(f"  {detail_line}")

    lines.extend(
        [
            "",
            "## Snapshot summary",
            f"- release_preview: {preview.get('status', '-')}",
            f"- announcement_pack: {announcement.get('status', '-')}",
            f"- release_assets: {assets.get('status', '-')}",
            f"- test_suite: {tests.get('status', '-')}",
            f"- oss_hygiene: {oss_hygiene.get('status', '-')}",
            "",
            "## Publish commands",
        ]
    )
    for command in _list(commands.get("publish")):
        lines.append(f"- `{command}`")
    if artifacts:
        lines.extend(
            [
                "",
                "## Artifact outputs",
                f"- checklist_json: {artifacts.get('json_path', '-')}",
                f"- checklist_markdown: {artifacts.get('markdown_path', '-')}",
                f"- release_preview_notes: {_mapping(artifacts, 'preview').get('notes_markdown_path', '-')}",
                f"- release_asset_summary: {_mapping(artifacts, 'assets').get('asset_summary_path', '-')}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_release_checklist_text(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot, "summary")
    target = _mapping(snapshot, "target")
    lines = [
        "Release preflight checklist:",
        f"- status: {summary.get('status', '-')}",
        f"- ready_to_publish: {summary.get('ready_to_publish', False)}",
        f"- message: {summary.get('message', '-')}",
        f"- target: {target.get('tag', '-')}",
        "",
        "Checks:",
    ]
    for item in _list(snapshot.get("checklist")):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {str(item.get('status', '-')).upper()} {item.get('name', 'Unnamed check')}: {item.get('message', '-')}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _build_oss_hygiene_snapshot(repo_root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for relative_path, label in OSS_RELEASE_REQUIRED_FILES:
        path = repo_root / relative_path
        exists = path.exists()
        checks.append(
            {
                "name": label,
                "path": str(path),
                "status": "ok" if exists else "error",
                "message": "present" if exists else "missing",
            }
        )
    missing = [item for item in checks if item["status"] == "error"]
    return {
        "status": "ok" if not missing else "error",
        "message": "Open-source release files are present."
        if not missing
        else "Open-source release files are missing.",
        "ok_count": len(checks) - len(missing),
        "missing_count": len(missing),
        "checks": checks,
    }


def _run_release_tests(
    *,
    repo_root: Path,
    run_tests: bool,
    test_command: Sequence[str] | None,
) -> dict[str, Any]:
    command = tuple(test_command or DEFAULT_RELEASE_TEST_COMMAND)
    if not run_tests:
        return {
            "ran": False,
            "status": "skipped",
            "command": " ".join(command),
            "return_code": None,
            "stdout": "",
            "stderr": "",
            "message": "Release test suite was skipped.",
        }
    completed = subprocess.run(
        list(command),
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ran": True,
        "status": "ok" if completed.returncode == 0 else "error",
        "command": " ".join(command),
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "message": "Release test suite passed."
        if completed.returncode == 0
        else "Release test suite failed.",
    }


def _build_release_checklist_items(
    *,
    preview_snapshot: dict[str, Any],
    announcement_snapshot: dict[str, Any],
    assets_snapshot: dict[str, Any],
    oss_hygiene: dict[str, Any],
    tests: dict[str, Any],
) -> list[dict[str, Any]]:
    items = [copy.deepcopy(check) for check in _list(preview_snapshot.get("checks")) if isinstance(check, dict)]
    items.append(_build_announcement_check(announcement_snapshot))
    items.append(_build_oss_hygiene_check(oss_hygiene))
    items.append(_build_test_check(tests))
    items.append(_build_build_check(_mapping(assets_snapshot, "build")))
    items.append(
        _build_dist_artifact_check(
            summary=_mapping(assets_snapshot, "summary"),
            artifacts=_list(assets_snapshot.get("artifacts")),
        )
    )
    items.append(_build_smoke_install_check(_mapping(assets_snapshot, "smoke_install")))
    return items


def _build_announcement_check(snapshot: dict[str, Any]) -> dict[str, Any]:
    summary = _mapping(snapshot, "summary")
    snippet_count = int(summary.get("snippet_count", 0) or 0)
    if snippet_count <= 0:
        return {
            "name": "Announcement pack",
            "status": "error",
            "message": "release announcement snippets were not generated",
            "hint": "Generate release announcement snippets before publishing the public preview.",
            "detail_lines": (),
        }
    return {
        "name": "Announcement pack",
        "status": "ok",
        "message": f"prepared {snippet_count} release announcement snippets",
        "hint": None,
        "detail_lines": (),
    }


def _build_oss_hygiene_check(snapshot: dict[str, Any]) -> dict[str, Any]:
    checks = _list(snapshot.get("checks"))
    missing = [item for item in checks if isinstance(item, dict) and item.get("status") == "error"]
    detail_lines = tuple(
        f"- {item.get('name', 'Missing file')}: {item.get('path', '-')}" for item in missing[:10]
    )
    if missing:
        return {
            "name": "Open-source release files",
            "status": "error",
            "message": f"{len(missing)} required governance or release file(s) are missing",
            "hint": "Restore the missing governance, release, or CI files before publishing.",
            "detail_lines": detail_lines,
        }
    return {
        "name": "Open-source release files",
        "status": "ok",
        "message": "governance, release, and CI files are present",
        "hint": None,
        "detail_lines": (),
    }


def _build_test_check(snapshot: dict[str, Any]) -> dict[str, Any]:
    detail_lines = (f"- command: {snapshot.get('command', '-')}",)
    status = str(snapshot.get("status") or "unknown")
    if status == "skipped":
        return {
            "name": "Release test suite",
            "status": "skipped",
            "message": "release test suite was skipped",
            "hint": "Run the release test suite before publishing when you want the full preflight gate.",
            "detail_lines": detail_lines,
        }
    if status == "error":
        return {
            "name": "Release test suite",
            "status": "error",
            "message": "release test suite failed",
            "hint": "Fix the failing tests and re-run the release preflight.",
            "detail_lines": detail_lines,
        }
    return {
        "name": "Release test suite",
        "status": "ok",
        "message": "release test suite passed",
        "hint": None,
        "detail_lines": detail_lines,
    }


def _build_build_check(snapshot: dict[str, Any]) -> dict[str, Any]:
    detail_lines = (f"- command: {snapshot.get('command', '-')}",)
    if not bool(snapshot.get("ran")):
        return {
            "name": "Artifact build",
            "status": "skipped",
            "message": "artifact build step was skipped",
            "hint": "Run the build step when you want the preflight to rebuild wheel and sdist from source.",
            "detail_lines": detail_lines,
        }
    if snapshot.get("status") == "error":
        return {
            "name": "Artifact build",
            "status": "error",
            "message": "artifact build failed",
            "hint": "Fix the build failure before uploading release artifacts.",
            "detail_lines": detail_lines,
        }
    return {
        "name": "Artifact build",
        "status": "ok",
        "message": "artifact build passed",
        "hint": None,
        "detail_lines": detail_lines,
    }


def _build_dist_artifact_check(
    *,
    summary: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    detail_lines = tuple(
        f"- {item.get('name', '-')}: sha256={item.get('sha256', '-')}" for item in artifacts[:5]
    )
    if summary.get("status") == "issues":
        return {
            "name": "Release assets",
            "status": "error",
            "message": str(summary.get("message") or "release assets have blocking issues"),
            "hint": "Ensure both wheel and sdist exist and match the target version.",
            "detail_lines": detail_lines,
        }
    if summary.get("status") == "attention":
        return {
            "name": "Release assets",
            "status": "warn",
            "message": str(summary.get("message") or "release assets need follow-up"),
            "hint": "Resolve version mismatches before uploading release artifacts.",
            "detail_lines": detail_lines,
        }
    return {
        "name": "Release assets",
        "status": "ok",
        "message": str(summary.get("message") or "release assets are ready"),
        "hint": None,
        "detail_lines": detail_lines,
    }


def _build_smoke_install_check(snapshot: dict[str, Any]) -> dict[str, Any]:
    detail_lines = (f"- command: {snapshot.get('command', '-')}",)
    if not bool(snapshot.get("ran")):
        return {
            "name": "Wheel smoke install",
            "status": "skipped",
            "message": "wheel smoke install was skipped",
            "hint": "Run smoke install when you want the preflight to verify `republic --help` from the built wheel.",
            "detail_lines": detail_lines,
        }
    if snapshot.get("status") == "error":
        return {
            "name": "Wheel smoke install",
            "status": "error",
            "message": "wheel smoke install failed",
            "hint": "Fix the built wheel or entry-point install path before publishing.",
            "detail_lines": detail_lines,
        }
    return {
        "name": "Wheel smoke install",
        "status": "ok",
        "message": "wheel smoke install passed",
        "hint": None,
        "detail_lines": detail_lines,
    }


def _build_release_checklist_summary(
    *,
    checklist: list[dict[str, Any]],
    target_tag: str,
) -> dict[str, Any]:
    error_count = sum(1 for item in checklist if item.get("status") == "error")
    warning_count = sum(1 for item in checklist if item.get("status") == "warn")
    skipped_count = sum(1 for item in checklist if item.get("status") == "skipped")
    ok_count = sum(1 for item in checklist if item.get("status") == "ok")
    if error_count:
        status = "issues"
        message = f"Release preflight for {target_tag} has blocking issues."
    elif warning_count:
        status = "attention"
        message = f"Release preflight for {target_tag} needs follow-up before publish."
    else:
        status = "clean"
        message = f"Release preflight for {target_tag} is ready for publish."
    return {
        "status": status,
        "message": message,
        "ready_to_publish": status == "clean",
        "ok_count": ok_count,
        "warning_count": warning_count,
        "error_count": error_count,
        "skipped_count": skipped_count,
        "check_count": len(checklist),
    }


def _public_release_checklist_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    materialized = copy.deepcopy(snapshot)
    for key in ("_preview_snapshot", "_announcement_snapshot", "_assets_snapshot"):
        materialized.pop(key, None)
    return materialized


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
