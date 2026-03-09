from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reporepublic.config import LoadedConfig
from reporepublic.release_preview import build_release_preview_snapshot
from reporepublic.utils.files import write_text_file


VALID_RELEASE_ANNOUNCEMENT_FORMATS = ("json", "markdown")


@dataclass(frozen=True, slots=True)
class ReleaseAnnouncementBuildResult:
    output_paths: dict[str, Path]
    snippet_paths: dict[str, Path]
    snapshot: dict[str, Any]


def normalize_release_announcement_formats(
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
            for item in VALID_RELEASE_ANNOUNCEMENT_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_RELEASE_ANNOUNCEMENT_FORMATS:
            raise ValueError(
                "Unsupported release announcement format. Expected one of: json, markdown, all"
            )
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def resolve_release_announcement_export_paths(
    target: Path,
    formats: tuple[str, ...],
) -> dict[str, Path]:
    resolved = target.resolve()
    export_paths: dict[str, Path] = {}
    for export_format in formats:
        suffix = ".md" if export_format == "markdown" else ".json"
        export_paths[export_format] = resolved.with_suffix(suffix)
    return export_paths


def build_release_announcement_snapshot(
    *,
    loaded: LoadedConfig | None = None,
    repo_root: Path | None = None,
    target_version: str | None = None,
    target_tag: str | None = None,
) -> dict[str, Any]:
    preview = build_release_preview_snapshot(
        loaded=loaded,
        repo_root=repo_root,
        target_version=target_version,
        target_tag=target_tag,
    )
    target = _mapping(preview, "target")
    summary = _mapping(preview, "summary")
    changelog = _mapping(preview, "changelog")
    commands = _mapping(preview, "commands")

    highlights = _extract_highlights(str(changelog.get("unreleased_body") or ""))
    release_notes = _mapping(preview, "release_notes")
    release_title = str(target.get("title") or f"RepoRepublic {target.get('tag', '')}")
    tag = str(target.get("tag") or "")
    version = str(target.get("version") or "")

    copy_pack = {
        "announcement": _build_announcement_copy(
            title=release_title,
            tag=tag,
            version=version,
            highlights=highlights,
        ),
        "discussion": _build_discussion_copy(
            title=release_title,
            tag=tag,
            highlights=highlights,
        ),
        "social": _build_social_copy(
            tag=tag,
            highlights=highlights,
        ),
        "release_cut": _build_release_cut_copy(
            tag=tag,
            version=version,
            commands=commands,
        ),
        "release_notes": str(release_notes.get("body") or "").rstrip() + "\n",
    }
    return {
        "meta": {
            "kind": "release_announcement",
            "repo_root": preview["meta"]["repo_root"],
            "rendered_at": preview["meta"]["rendered_at"],
        },
        "summary": {
            "status": summary.get("status", "unknown"),
            "message": f"Prepared announcement copy pack for {tag}.",
            "preview_status": summary.get("status", "unknown"),
            "preview_message": summary.get("message", ""),
            "snippet_count": len(copy_pack),
        },
        "target": target,
        "highlights": highlights,
        "preview": {
            "status": summary.get("status", "unknown"),
            "warning_count": summary.get("warning_count", 0),
            "error_count": summary.get("error_count", 0),
        },
        "copy_pack": copy_pack,
    }


def build_release_announcement_exports(
    *,
    snapshot: dict[str, Any],
    output_path: Path,
    formats: tuple[str, ...],
) -> ReleaseAnnouncementBuildResult:
    export_paths = resolve_release_announcement_export_paths(output_path, formats)
    snippet_paths = _resolve_snippet_paths(output_path, snapshot)
    for key, path in snippet_paths.items():
        write_text_file(path, str(snapshot["copy_pack"][key]).rstrip() + "\n")

    materialized_snapshot = copy.deepcopy(snapshot)
    materialized_snapshot["artifacts"] = {
        "json_path": str(export_paths["json"]) if "json" in export_paths else None,
        "markdown_path": str(export_paths["markdown"]) if "markdown" in export_paths else None,
        "snippet_paths": {key: str(path) for key, path in snippet_paths.items()},
    }

    if "json" in export_paths:
        write_text_file(export_paths["json"], render_release_announcement_json(materialized_snapshot))
    if "markdown" in export_paths:
        write_text_file(
            export_paths["markdown"],
            render_release_announcement_markdown(materialized_snapshot),
        )
    return ReleaseAnnouncementBuildResult(
        output_paths=export_paths,
        snippet_paths=snippet_paths,
        snapshot=materialized_snapshot,
    )


def render_release_announcement_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True)


def render_release_announcement_markdown(snapshot: dict[str, Any]) -> str:
    meta = _mapping(snapshot, "meta")
    summary = _mapping(snapshot, "summary")
    target = _mapping(snapshot, "target")
    preview = _mapping(snapshot, "preview")
    artifacts = _mapping(snapshot, "artifacts")
    highlights = _list(snapshot.get("highlights"))
    copy_pack = _mapping(snapshot, "copy_pack")

    lines = [
        "# Release announcement pack",
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
        "",
        "## Release preview posture",
        f"- status: {preview.get('status', '-')}",
        f"- warning_count: {preview.get('warning_count', 0)}",
        f"- error_count: {preview.get('error_count', 0)}",
        "",
        "## Snippet files",
    ]
    for key, value in _mapping(artifacts, "snippet_paths").items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Highlights"])
    if highlights:
        lines.extend(f"- {item}" for item in highlights)
    else:
        lines.append("- none")

    for key in ("announcement", "discussion", "social", "release_cut"):
        body = str(copy_pack.get(key) or "").rstrip()
        lines.extend(["", f"## {key.replace('_', ' ').title()}", "", body])
    return "\n".join(lines).rstrip() + "\n"


def render_release_announcement_text(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot, "summary")
    target = _mapping(snapshot, "target")
    preview = _mapping(snapshot, "preview")
    lines = [
        "Release announcement pack:",
        f"- status: {summary.get('status', '-')}",
        f"- message: {summary.get('message', '-')}",
        f"- target: {target.get('tag', '-')}",
        f"- preview_status: {preview.get('status', '-')}",
        f"- warning_count: {preview.get('warning_count', 0)}",
        f"- error_count: {preview.get('error_count', 0)}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _resolve_snippet_paths(output_path: Path, snapshot: dict[str, Any]) -> dict[str, Path]:
    target_tag = str(snapshot["target"]["tag"])
    root = output_path.resolve().parent
    return {
        "announcement": root / f"announcement-{target_tag}.md",
        "discussion": root / f"discussion-{target_tag}.md",
        "social": root / f"social-{target_tag}.md",
        "release_cut": root / f"release-cut-{target_tag}.md",
        "release_notes": root / f"release-notes-{target_tag}.md",
    }


def _build_announcement_copy(
    *,
    title: str,
    tag: str,
    version: str,
    highlights: list[str],
) -> str:
    lines = [
        f"# {title}",
        "",
        f"RepoRepublic {tag} is now available as a public preview.",
        "",
        "RepoRepublic installs an AI maintainer team into any repo, with Codex CLI as the default live worker runtime and human approval as the default safety boundary.",
        "",
        "## Highlights",
    ]
    lines.extend(f"- {item}" for item in highlights)
    lines.extend(
        [
            "",
            "## Start here",
            "- README: https://github.com/lhy0718/RepoRepublic",
            "- Quickstart: https://github.com/lhy0718/RepoRepublic/blob/main/QUICKSTART.md",
            "- Release checklist: https://github.com/lhy0718/RepoRepublic/blob/main/docs/release.md",
            "",
            f"Tag: `{tag}`",
            f"Version: `{version}`",
        ]
    )
    return "\n".join(lines)


def _build_discussion_copy(
    *,
    title: str,
    tag: str,
    highlights: list[str],
) -> str:
    lines = [
        f"# {title} public preview",
        "",
        f"We have cut `{tag}` as the first public preview of RepoRepublic.",
        "",
        "What we want feedback on:",
        "- CLI-first maintainer workflow clarity",
        "- GitHub live-ops rollout guardrails",
        "- sync / ops handoff surface usefulness",
        "",
        "What is included in this preview:",
    ]
    lines.extend(f"- {item}" for item in highlights)
    lines.extend(
        [
            "",
            "Where to start:",
            "- README and Quickstart for first-run setup",
            "- `examples/live-github-ops` for rollout rehearsal",
            "- `examples/live-github-sandbox-rollout` for publish-enabled sandbox gating",
            "",
            "If you try it in a real repository, please share:",
            "- the first command that felt unclear",
            "- the first safety/policy guardrail that felt missing",
            "- the first report or bundle artifact that actually helped",
        ]
    )
    return "\n".join(lines)


def _build_social_copy(
    *,
    tag: str,
    highlights: list[str],
) -> str:
    first_highlight = highlights[0] if highlights else "CLI-first AI maintainer orchestration for repositories."
    second_highlight = highlights[1] if len(highlights) > 1 else "Codex CLI is the default live worker runtime."
    return "\n".join(
        [
            f"RepoRepublic {tag} is out in public preview.",
            "Install an AI maintainer team into any repo.",
            first_highlight,
            second_highlight,
            "GitHub: https://github.com/lhy0718/RepoRepublic",
        ]
    )


def _build_release_cut_copy(
    *,
    tag: str,
    version: str,
    commands: dict[str, Any],
) -> str:
    prepare = _list(commands.get("prepare"))
    verify = _list(commands.get("verify"))
    publish = _list(commands.get("publish"))
    lines = [
        f"# Release cut checklist for {tag}",
        "",
        f"- target_version: {version}",
        f"- target_tag: {tag}",
        "",
        "## Prepare",
    ]
    lines.extend(f"{index}. `{command}`" for index, command in enumerate(prepare, start=1))
    lines.extend(["", "## Verify"])
    lines.extend(f"{index}. `{command}`" for index, command in enumerate(verify, start=1))
    lines.extend(["", "## Publish"])
    lines.extend(f"{index}. `{command}`" for index, command in enumerate(publish, start=1))
    return "\n".join(lines)


def _extract_highlights(unreleased_body: str) -> list[str]:
    highlights: list[str] = []
    for line in unreleased_body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            highlights.append(stripped[2:].strip())
    if not highlights:
        highlights.append("RepoRepublic public preview release.")
    return highlights[:4]


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
