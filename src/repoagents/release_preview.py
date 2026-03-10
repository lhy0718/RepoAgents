from __future__ import annotations

import copy
import json
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from repoagents.config import LoadedConfig
from repoagents.models.domain import utc_now
from repoagents.utils.files import write_text_file
from repoagents.utils.git import GitCommandError, is_git_repository, list_dirty_working_tree_entries, run_git


VALID_RELEASE_PREVIEW_FORMATS = ("json", "markdown")
CHANGELOG_SECTION_PATTERN = re.compile(
    r"^## \[(?P<name>[^\]]+)\](?: - (?P<released_on>[^\n]+))?$",
    re.MULTILINE,
)
VERSION_PATTERN = re.compile(r'__version__\s*=\s*"(?P<version>[^"]+)"')


@dataclass(frozen=True, slots=True)
class ReleasePreviewBuildResult:
    output_paths: dict[str, Path]
    notes_markdown_path: Path
    snapshot: dict[str, Any]


def normalize_release_preview_formats(
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
            for item in VALID_RELEASE_PREVIEW_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_RELEASE_PREVIEW_FORMATS:
            raise ValueError(
                "Unsupported release preview format. Expected one of: json, markdown, all"
            )
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def resolve_release_preview_export_paths(
    target: Path,
    formats: tuple[str, ...],
) -> dict[str, Path]:
    resolved = target.resolve()
    export_paths: dict[str, Path] = {}
    for export_format in formats:
        suffix = ".md" if export_format == "markdown" else ".json"
        export_paths[export_format] = resolved.with_suffix(suffix)
    return export_paths


def build_release_preview_snapshot(
    *,
    loaded: LoadedConfig | None = None,
    repo_root: Path | None = None,
    target_version: str | None = None,
    target_tag: str | None = None,
) -> dict[str, Any]:
    resolved_repo_root = (loaded.repo_root if loaded is not None else (repo_root or Path.cwd())).resolve()
    rendered_at = utc_now().isoformat()
    pyproject_path = resolved_repo_root / "pyproject.toml"
    changelog_path = resolved_repo_root / "CHANGELOG.md"
    package_init_path = resolved_repo_root / "src" / "repoagents" / "__init__.py"

    pyproject_version = _load_pyproject_version(pyproject_path)
    module_version = _load_package_version(package_init_path)
    base_version = pyproject_version or module_version or "0.0.0"

    changelog_exists = changelog_path.exists()
    changelog_text = changelog_path.read_text(encoding="utf-8") if changelog_exists else ""
    changelog_sections = _parse_changelog_sections(changelog_text)
    unreleased_body = changelog_sections.get("Unreleased", {}).get("body", "")
    unreleased_entries = _extract_markdown_bullets(unreleased_body)

    resolved_target_version, version_source, version_reason = _resolve_target_version(
        explicit_version=target_version,
        current_version=base_version,
        current_version_released=base_version in changelog_sections,
        unreleased_entry_count=len(unreleased_entries),
    )
    resolved_target_tag = target_tag or f"v{resolved_target_version}"
    release_title = f"RepoAgents {resolved_target_tag}"
    release_date = date.today().isoformat()

    working_tree = _collect_working_tree_snapshot(resolved_repo_root)
    checks = [
        _build_version_file_check(
            pyproject_version=pyproject_version,
            module_version=module_version,
            pyproject_path=pyproject_path,
            package_init_path=package_init_path,
        ),
        _build_target_check(
            resolved_target_version=resolved_target_version,
            resolved_target_tag=resolved_target_tag,
            current_version=base_version,
            changelog_sections=changelog_sections,
        ),
        _build_changelog_check(
            changelog_exists=changelog_exists,
            changelog_path=changelog_path,
            unreleased_body=unreleased_body,
            unreleased_entry_count=len(unreleased_entries),
        ),
        _build_working_tree_check(working_tree),
        _build_branch_check(working_tree),
    ]

    files_to_update = _determine_files_to_update(
        resolved_target_version=resolved_target_version,
        pyproject_version=pyproject_version,
        module_version=module_version,
    )
    release_notes_body = _build_release_notes_body(
        target_version=resolved_target_version,
        target_tag=resolved_target_tag,
        release_title=release_title,
        unreleased_body=unreleased_body,
    )
    commands = _build_release_commands(
        resolved_target_version=resolved_target_version,
        resolved_target_tag=resolved_target_tag,
        release_date=release_date,
        files_to_update=files_to_update,
    )
    summary = _build_summary(
        checks=checks,
        resolved_target_version=resolved_target_version,
        resolved_target_tag=resolved_target_tag,
    )

    return {
        "meta": {
            "kind": "release_preview",
            "rendered_at": rendered_at,
            "repo_root": str(resolved_repo_root),
            "pyproject_path": str(pyproject_path),
            "changelog_path": str(changelog_path),
            "package_init_path": str(package_init_path),
        },
        "summary": summary,
        "target": {
            "version": resolved_target_version,
            "tag": resolved_target_tag,
            "title": release_title,
            "release_date": release_date,
            "source": version_source,
            "source_reason": version_reason,
            "current_version": base_version,
            "pyproject_version": pyproject_version,
            "module_version": module_version,
        },
        "changelog": {
            "exists": changelog_exists,
            "sections": sorted(changelog_sections),
            "unreleased_entry_count": len(unreleased_entries),
            "unreleased_body": unreleased_body.strip(),
            "current_version_released": base_version in changelog_sections,
            "target_version_exists": resolved_target_version in changelog_sections,
        },
        "working_tree": working_tree,
        "checks": checks,
        "files_to_update": files_to_update,
        "commands": commands,
        "release_notes": {
            "title": release_title,
            "body": release_notes_body,
        },
    }


def build_release_preview_exports(
    *,
    snapshot: dict[str, Any],
    output_path: Path,
    formats: tuple[str, ...],
) -> ReleasePreviewBuildResult:
    export_paths = resolve_release_preview_export_paths(output_path, formats)
    notes_markdown_path = output_path.resolve().with_name(
        f"release-notes-{snapshot['target']['tag']}.md"
    )
    write_text_file(notes_markdown_path, snapshot["release_notes"]["body"].rstrip() + "\n")

    materialized_snapshot = _attach_export_artifacts(
        snapshot=snapshot,
        export_paths=export_paths,
        notes_markdown_path=notes_markdown_path,
    )
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_release_preview_json(materialized_snapshot))
    if "markdown" in export_paths:
        write_text_file(
            export_paths["markdown"],
            render_release_preview_markdown(
                materialized_snapshot,
                notes_markdown_path=notes_markdown_path,
            ),
        )
    return ReleasePreviewBuildResult(
        output_paths=export_paths,
        notes_markdown_path=notes_markdown_path,
        snapshot=materialized_snapshot,
    )


def render_release_preview_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True)


def render_release_preview_markdown(
    snapshot: dict[str, Any],
    *,
    notes_markdown_path: Path | None = None,
) -> str:
    meta = _mapping(snapshot, "meta")
    summary = _mapping(snapshot, "summary")
    target = _mapping(snapshot, "target")
    changelog = _mapping(snapshot, "changelog")
    working_tree = _mapping(snapshot, "working_tree")
    artifacts = _mapping(snapshot, "artifacts")
    commands = _mapping(snapshot, "commands")
    checks = _list(snapshot.get("checks"))
    files_to_update = _list(snapshot.get("files_to_update"))
    notes = _mapping(snapshot, "release_notes")

    lines = [
        "# Release preview",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- status: {summary.get('status', '-')}",
        f"- message: {summary.get('message', '-')}",
        "",
        "## Target",
        f"- version: {target.get('version', '-')}",
        f"- tag: {target.get('tag', '-')}",
        f"- title: {target.get('title', '-')}",
        f"- release_date: {target.get('release_date', '-')}",
        f"- source: {target.get('source', '-')}",
        f"- source_reason: {target.get('source_reason', '-')}",
        f"- current_version: {target.get('current_version', '-')}",
        f"- pyproject_version: {target.get('pyproject_version', '-')}",
        f"- module_version: {target.get('module_version', '-')}",
        "",
        "## Changelog",
        f"- exists: {changelog.get('exists', '-')}",
        f"- unreleased_entry_count: {changelog.get('unreleased_entry_count', 0)}",
        f"- current_version_released: {changelog.get('current_version_released', False)}",
        f"- target_version_exists: {changelog.get('target_version_exists', False)}",
        "",
        "## Working tree",
        f"- status: {working_tree.get('status', '-')}",
        f"- branch: {working_tree.get('branch', '-')}",
        f"- dirty_entry_count: {working_tree.get('dirty_entry_count', 0)}",
    ]
    dirty_entries = _list(working_tree.get("dirty_entries"))
    if dirty_entries:
        lines.append("- dirty_entries:")
        lines.extend(f"  - {entry}" for entry in dirty_entries[:10])

    lines.extend(["", "## Checks"])
    for check in checks:
        if not isinstance(check, dict):
            continue
        lines.extend(
            [
                "",
                f"### {check.get('name', 'Unknown check')}",
                f"- status: {check.get('status', '-')}",
                f"- message: {check.get('message', '-')}",
            ]
        )
        if check.get("hint"):
            lines.append(f"- hint: {check['hint']}")
        for detail in _list(check.get("detail_lines")):
            lines.append(f"  {detail}")

    lines.extend(["", "## Files to update"])
    if files_to_update:
        lines.extend(f"- {item}" for item in files_to_update)
    else:
        lines.append("- none")

    lines.extend(["", "## Command order"])
    for section_name in ("prepare", "verify", "publish"):
        section_commands = _list(commands.get(section_name))
        lines.extend(["", f"### {section_name}"])
        if section_commands:
            lines.extend(f"{index}. `{command}`" for index, command in enumerate(section_commands, start=1))
        else:
            lines.append("- none")

    lines.extend(
        [
            "",
            "## GitHub release body",
            f"- notes_path: {notes_markdown_path or artifacts.get('notes_markdown_path', '-')}",
            "",
            notes.get("body", "").rstrip(),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_release_preview_text(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot, "summary")
    target = _mapping(snapshot, "target")
    working_tree = _mapping(snapshot, "working_tree")
    checks = _list(snapshot.get("checks"))
    commands = _mapping(snapshot, "commands")

    lines = [
        "Release preview:",
        f"- status: {summary.get('status', '-')}",
        f"- message: {summary.get('message', '-')}",
        f"- version: {target.get('version', '-')}",
        f"- tag: {target.get('tag', '-')}",
        f"- source: {target.get('source', '-')} ({target.get('source_reason', '-')})",
        f"- branch: {working_tree.get('branch', '-')}",
        f"- working_tree: {working_tree.get('status', '-')}",
        "",
        "Checks:",
    ]
    for check in checks:
        if not isinstance(check, dict):
            continue
        lines.append(
            f"- {str(check.get('status', '-')).upper()} {check.get('name', 'Unknown check')}: {check.get('message', '-')}"
        )
    lines.extend(["", "Command order:"])
    for command in _list(commands.get("prepare"))[:3]:
        lines.append(f"- prepare: {command}")
    for command in _list(commands.get("verify"))[:3]:
        lines.append(f"- verify: {command}")
    for command in _list(commands.get("publish"))[:3]:
        lines.append(f"- publish: {command}")
    return "\n".join(lines).rstrip() + "\n"


def _attach_export_artifacts(
    *,
    snapshot: dict[str, Any],
    export_paths: dict[str, Path],
    notes_markdown_path: Path,
) -> dict[str, Any]:
    materialized = copy.deepcopy(snapshot)
    materialized["artifacts"] = {
        "json_path": str(export_paths["json"]) if "json" in export_paths else None,
        "markdown_path": str(export_paths["markdown"]) if "markdown" in export_paths else None,
        "notes_markdown_path": str(notes_markdown_path),
    }
    return materialized


def _load_pyproject_version(pyproject_path: Path) -> str | None:
    if not pyproject_path.exists():
        return None
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    return str(version) if version else None


def _load_package_version(package_init_path: Path) -> str | None:
    if not package_init_path.exists():
        return None
    match = VERSION_PATTERN.search(package_init_path.read_text(encoding="utf-8"))
    if match is None:
        return None
    return match.group("version").strip()


def _parse_changelog_sections(body: str) -> dict[str, dict[str, str]]:
    matches = list(CHANGELOG_SECTION_PATTERN.finditer(body))
    sections: dict[str, dict[str, str]] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group("name")] = {
            "released_on": (match.group("released_on") or "").strip(),
            "body": body[start:end].strip(),
        }
    return sections


def _extract_markdown_bullets(body: str) -> list[str]:
    entries: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            entries.append(stripped[2:].strip())
    return entries


def _resolve_target_version(
    *,
    explicit_version: str | None,
    current_version: str,
    current_version_released: bool,
    unreleased_entry_count: int,
) -> tuple[str, str, str]:
    if explicit_version:
        return (
            explicit_version,
            "explicit",
            "used the version supplied via --version",
        )
    if current_version_released and unreleased_entry_count > 0:
        bumped = _bump_patch_version(current_version)
        if bumped != current_version:
            return (
                bumped,
                "inferred_patch_bump",
                f"inferred next patch release because {current_version} already has a dated changelog section",
            )
    return (
        current_version,
        "current_version",
        "used the current project version because no explicit target version was supplied",
    )


def _bump_patch_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return version
    major, minor, patch = (int(part) for part in parts)
    return f"{major}.{minor}.{patch + 1}"


def _collect_working_tree_snapshot(repo_root: Path) -> dict[str, Any]:
    is_repo = is_git_repository(repo_root)
    branch = None
    dirty_entries: list[str] = []
    git_error = None
    if is_repo:
        try:
            branch = run_git(["branch", "--show-current"], repo_root).strip() or None
            dirty_entries = list_dirty_working_tree_entries(repo_root)
        except GitCommandError as exc:
            git_error = str(exc)
    status = "clean"
    if not is_repo:
        status = "not_git"
    elif git_error is not None:
        status = "error"
    elif dirty_entries:
        status = "dirty"
    return {
        "status": status,
        "branch": branch,
        "is_git_repo": is_repo,
        "dirty_entry_count": len(dirty_entries),
        "dirty_entries": dirty_entries,
        "git_error": git_error,
    }


def _build_version_file_check(
    *,
    pyproject_version: str | None,
    module_version: str | None,
    pyproject_path: Path,
    package_init_path: Path,
) -> dict[str, Any]:
    detail_lines = (
        f"- pyproject: {pyproject_path}",
        f"- package_init: {package_init_path}",
    )
    if pyproject_version is None:
        return {
            "name": "Version files",
            "status": "error",
            "message": "pyproject.toml does not define project.version",
            "hint": "Add or restore project.version before cutting a public release.",
            "detail_lines": detail_lines,
        }
    if module_version is None:
        return {
            "name": "Version files",
            "status": "error",
            "message": "src/repoagents/__init__.py does not define __version__",
            "hint": "Restore the package __version__ marker before tagging a release.",
            "detail_lines": detail_lines,
        }
    if pyproject_version != module_version:
        return {
            "name": "Version files",
            "status": "error",
            "message": f"pyproject.toml ({pyproject_version}) and package __version__ ({module_version}) differ",
            "hint": "Keep both version markers aligned before building release artifacts.",
            "detail_lines": detail_lines,
        }
    return {
        "name": "Version files",
        "status": "ok",
        "message": f"pyproject.toml and package __version__ both report {pyproject_version}",
        "hint": None,
        "detail_lines": detail_lines,
    }


def _build_target_check(
    *,
    resolved_target_version: str,
    resolved_target_tag: str,
    current_version: str,
    changelog_sections: dict[str, dict[str, str]],
) -> dict[str, Any]:
    detail_lines = (
        f"- target_version: {resolved_target_version}",
        f"- target_tag: {resolved_target_tag}",
        f"- current_version: {current_version}",
    )
    if resolved_target_version in changelog_sections:
        return {
            "name": "Release target",
            "status": "error",
            "message": f"CHANGELOG.md already contains a released section for {resolved_target_version}",
            "hint": "Choose a new version or move unreleased notes into a fresh release section.",
            "detail_lines": detail_lines,
        }
    if resolved_target_version != current_version:
        return {
            "name": "Release target",
            "status": "warn",
            "message": f"target release is {resolved_target_version} but version files still read {current_version}",
            "hint": "Update pyproject.toml and src/repoagents/__init__.py before tagging the release.",
            "detail_lines": detail_lines,
        }
    if resolved_target_tag != f"v{resolved_target_version}":
        return {
            "name": "Release target",
            "status": "warn",
            "message": f"tag {resolved_target_tag} does not follow the default v<version> pattern",
            "hint": "Use the default tag pattern unless you have a release-process reason not to.",
            "detail_lines": detail_lines,
        }
    return {
        "name": "Release target",
        "status": "ok",
        "message": f"target tag {resolved_target_tag} matches version {resolved_target_version}",
        "hint": None,
        "detail_lines": detail_lines,
    }


def _build_changelog_check(
    *,
    changelog_exists: bool,
    changelog_path: Path,
    unreleased_body: str,
    unreleased_entry_count: int,
) -> dict[str, Any]:
    detail_lines = (
        f"- changelog_path: {changelog_path}",
        f"- unreleased_entry_count: {unreleased_entry_count}",
    )
    if not changelog_exists:
        return {
            "name": "Changelog unreleased notes",
            "status": "error",
            "message": "CHANGELOG.md is missing",
            "hint": "Restore CHANGELOG.md and move public release notes through the Unreleased section.",
            "detail_lines": detail_lines,
        }
    if not unreleased_body.strip():
        return {
            "name": "Changelog unreleased notes",
            "status": "error",
            "message": "Unreleased changelog section is empty",
            "hint": "Add public-facing notes to CHANGELOG.md before cutting a preview release.",
            "detail_lines": detail_lines,
        }
    return {
        "name": "Changelog unreleased notes",
        "status": "ok",
        "message": f"captured {unreleased_entry_count} unreleased bullet(s) for the release body preview",
        "hint": None,
        "detail_lines": detail_lines,
    }


def _build_working_tree_check(working_tree: dict[str, Any]) -> dict[str, Any]:
    detail_lines = tuple(f"- {entry}" for entry in _list(working_tree.get("dirty_entries"))[:10])
    status = str(working_tree.get("status") or "unknown")
    if status == "not_git":
        return {
            "name": "Working tree",
            "status": "warn",
            "message": "repository is not inside a git work tree",
            "hint": "Run the release preview from the tracked repository root before tagging a release.",
            "detail_lines": (),
        }
    if status == "error":
        return {
            "name": "Working tree",
            "status": "warn",
            "message": str(working_tree.get("git_error") or "could not inspect git working tree"),
            "hint": "Resolve the git inspection failure before tagging a release.",
            "detail_lines": detail_lines,
        }
    if status == "dirty":
        return {
            "name": "Working tree",
            "status": "warn",
            "message": f"working tree has {working_tree.get('dirty_entry_count', 0)} uncommitted change(s)",
            "hint": "Commit or stash local changes before creating the release tag.",
            "detail_lines": detail_lines,
        }
    return {
        "name": "Working tree",
        "status": "ok",
        "message": "working tree is clean",
        "hint": None,
        "detail_lines": (),
    }


def _build_branch_check(working_tree: dict[str, Any]) -> dict[str, Any]:
    branch = str(working_tree.get("branch") or "")
    if not branch:
        return {
            "name": "Release branch",
            "status": "warn",
            "message": "current git branch could not be determined",
            "hint": "Cut public releases from main unless your release process explicitly uses another branch.",
            "detail_lines": (),
        }
    if branch != "main":
        return {
            "name": "Release branch",
            "status": "warn",
            "message": f"current branch is {branch}, not main",
            "hint": "Verify you are releasing from the intended branch before pushing the tag.",
            "detail_lines": (f"- branch: {branch}",),
        }
    return {
        "name": "Release branch",
        "status": "ok",
        "message": "current branch is main",
        "hint": None,
        "detail_lines": (f"- branch: {branch}",),
    }


def _determine_files_to_update(
    *,
    resolved_target_version: str,
    pyproject_version: str | None,
    module_version: str | None,
) -> list[str]:
    files = ["CHANGELOG.md"]
    if pyproject_version != resolved_target_version:
        files.append("pyproject.toml")
    if module_version != resolved_target_version:
        files.append("src/repoagents/__init__.py")
    return files


def _build_release_commands(
    *,
    resolved_target_version: str,
    resolved_target_tag: str,
    release_date: str,
    files_to_update: list[str],
) -> dict[str, list[str]]:
    tracked_files = " ".join(files_to_update)
    prepare_commands = [
        f"# update {', '.join(files_to_update)} for {resolved_target_version}",
        f"# move Unreleased notes into ## [{resolved_target_version}] - {release_date} in CHANGELOG.md",
        f"git add {tracked_files}",
        f'git commit -m "release: {resolved_target_tag}"',
    ]
    verify_commands = [
        "uv sync --dev",
        "uv run pytest -q",
        "uv build",
        "python3.12 -m venv /tmp/repoagents-release-smoke",
        "/tmp/repoagents-release-smoke/bin/pip install dist/*.whl",
        "/tmp/repoagents-release-smoke/bin/repoagents --help",
    ]
    publish_commands = [
        f'git tag -a {resolved_target_tag} -m "RepoAgents {resolved_target_tag}"',
        "git push origin main",
        f"git push origin {resolved_target_tag}",
        (
            f'gh release create {resolved_target_tag} --title "RepoAgents {resolved_target_tag}" '
            f'--notes-file .ai-repoagents/reports/release-notes-{resolved_target_tag}.md'
        ),
    ]
    return {
        "prepare": prepare_commands,
        "verify": verify_commands,
        "publish": publish_commands,
    }


def _build_release_notes_body(
    *,
    target_version: str,
    target_tag: str,
    release_title: str,
    unreleased_body: str,
) -> str:
    notes_body = unreleased_body.strip() or "- No unreleased notes captured yet."
    return "\n".join(
        [
            "## Highlights",
            notes_body,
            "",
            "## Verification",
            "- `uv run pytest -q`",
            "- `uv build`",
            "- clean wheel install smoke for `repoagents --help`",
            "",
            "## Operator defaults",
            "- Codex remains the default live worker runtime.",
            "- Auto-merge remains human approval by default.",
            "- Live GitHub write-path checks stay opt-in and should run only against a sandbox repo.",
            "",
            "## Release metadata",
            f"- title: {release_title}",
            f"- tag: {target_tag}",
            f"- version: {target_version}",
        ]
    ).rstrip() + "\n"


def _build_summary(
    *,
    checks: list[dict[str, Any]],
    resolved_target_version: str,
    resolved_target_tag: str,
) -> dict[str, Any]:
    error_count = sum(1 for check in checks if check.get("status") == "error")
    warning_count = sum(1 for check in checks if check.get("status") == "warn")
    ok_count = sum(1 for check in checks if check.get("status") == "ok")
    if error_count:
        status = "issues"
        message = f"Release preview for {resolved_target_tag} has blocking issues."
    elif warning_count:
        status = "attention"
        message = f"Release preview for {resolved_target_tag} needs follow-up before tagging."
    else:
        status = "clean"
        message = f"Release preview for {resolved_target_tag} is ready for tag cut."
    return {
        "status": status,
        "message": message,
        "target_version": resolved_target_version,
        "target_tag": resolved_target_tag,
        "ok_count": ok_count,
        "warning_count": warning_count,
        "error_count": error_count,
    }


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
