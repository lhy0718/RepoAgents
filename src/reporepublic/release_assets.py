from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reporepublic.config import LoadedConfig
from reporepublic.release_preview import build_release_preview_snapshot
from reporepublic.utils.files import write_text_file


VALID_RELEASE_ASSET_FORMATS = ("json", "markdown")


@dataclass(frozen=True, slots=True)
class ReleaseAssetsBuildResult:
    output_paths: dict[str, Path]
    asset_summary_path: Path
    snapshot: dict[str, Any]


def normalize_release_asset_formats(
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
            for item in VALID_RELEASE_ASSET_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_RELEASE_ASSET_FORMATS:
            raise ValueError(
                "Unsupported release asset format. Expected one of: json, markdown, all"
            )
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def resolve_release_asset_export_paths(
    target: Path,
    formats: tuple[str, ...],
) -> dict[str, Path]:
    resolved = target.resolve()
    export_paths: dict[str, Path] = {}
    for export_format in formats:
        suffix = ".md" if export_format == "markdown" else ".json"
        export_paths[export_format] = resolved.with_suffix(suffix)
    return export_paths


def build_release_asset_snapshot(
    *,
    loaded: LoadedConfig | None = None,
    repo_root: Path | None = None,
    target_version: str | None = None,
    target_tag: str | None = None,
    build: bool = False,
    smoke_install: bool = False,
    dist_dir: Path | None = None,
) -> dict[str, Any]:
    preview = build_release_preview_snapshot(
        loaded=loaded,
        repo_root=repo_root,
        target_version=target_version,
        target_tag=target_tag,
    )
    resolved_repo_root = Path(preview["meta"]["repo_root"]).resolve()
    target = _mapping(preview, "target")
    resolved_dist_dir = (dist_dir.resolve() if dist_dir is not None else (resolved_repo_root / "dist").resolve())

    build_result = _run_build(resolved_repo_root) if build else {
        "ran": False,
        "status": "skipped",
        "command": "uv build",
        "return_code": None,
        "stdout": "",
        "stderr": "",
    }
    artifacts = _collect_dist_artifacts(
        dist_dir=resolved_dist_dir,
        target_version=str(target.get("version") or ""),
    )
    smoke = _run_smoke_install(
        repo_root=resolved_repo_root,
        dist_dir=resolved_dist_dir,
        wheel_path=next((Path(item["path"]) for item in artifacts if item["kind"] == "wheel"), None),
    ) if smoke_install else {
        "ran": False,
        "status": "skipped",
        "command": None,
        "return_code": None,
        "stdout": "",
        "stderr": "",
    }
    commands = _build_release_asset_commands(
        tag=str(target.get("tag") or ""),
    )
    summary = _build_release_asset_summary(
        artifacts=artifacts,
        build_result=build_result,
        smoke=smoke,
    )
    return {
        "meta": {
            "kind": "release_assets",
            "repo_root": str(resolved_repo_root),
            "rendered_at": preview["meta"]["rendered_at"],
            "dist_dir": str(resolved_dist_dir),
        },
        "summary": summary,
        "target": target,
        "preview": {
            "status": preview["summary"]["status"],
            "message": preview["summary"]["message"],
        },
        "build": build_result,
        "artifacts": artifacts,
        "smoke_install": smoke,
        "commands": commands,
    }


def build_release_asset_exports(
    *,
    snapshot: dict[str, Any],
    output_path: Path,
    formats: tuple[str, ...],
) -> ReleaseAssetsBuildResult:
    export_paths = resolve_release_asset_export_paths(output_path, formats)
    asset_summary_path = output_path.resolve().with_name(
        f"release-assets-{snapshot['target']['tag']}.md"
    )
    write_text_file(asset_summary_path, render_release_asset_summary_markdown(snapshot))

    materialized = copy.deepcopy(snapshot)
    materialized["artifact_outputs"] = {
        "json_path": str(export_paths["json"]) if "json" in export_paths else None,
        "markdown_path": str(export_paths["markdown"]) if "markdown" in export_paths else None,
        "asset_summary_path": str(asset_summary_path),
    }
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_release_asset_json(materialized))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_release_asset_markdown(materialized))
    return ReleaseAssetsBuildResult(
        output_paths=export_paths,
        asset_summary_path=asset_summary_path,
        snapshot=materialized,
    )


def render_release_asset_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True)


def render_release_asset_markdown(snapshot: dict[str, Any]) -> str:
    meta = _mapping(snapshot, "meta")
    summary = _mapping(snapshot, "summary")
    target = _mapping(snapshot, "target")
    preview = _mapping(snapshot, "preview")
    build = _mapping(snapshot, "build")
    smoke = _mapping(snapshot, "smoke_install")
    commands = _mapping(snapshot, "commands")
    artifacts = _list(snapshot.get("artifacts"))
    outputs = _mapping(snapshot, "artifact_outputs")

    lines = [
        "# Release assets dry-run",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- dist_dir: {meta.get('dist_dir', '-')}",
        f"- status: {summary.get('status', '-')}",
        f"- message: {summary.get('message', '-')}",
        "",
        "## Target",
        f"- version: {target.get('version', '-')}",
        f"- tag: {target.get('tag', '-')}",
        f"- title: {target.get('title', '-')}",
        "",
        "## Preview posture",
        f"- status: {preview.get('status', '-')}",
        f"- message: {preview.get('message', '-')}",
        "",
        "## Build",
        f"- status: {build.get('status', '-')}",
        f"- ran: {build.get('ran', False)}",
        f"- command: {build.get('command', '-')}",
        f"- return_code: {build.get('return_code', '-')}",
        "",
        "## Dist artifacts",
    ]
    if artifacts:
        for artifact in artifacts:
            lines.extend(
                [
                    "",
                    f"### {artifact.get('name', 'artifact')}",
                    f"- kind: {artifact.get('kind', '-')}",
                    f"- version: {artifact.get('version', '-')}",
                    f"- version_matches_target: {artifact.get('version_matches_target', False)}",
                    f"- size_bytes: {artifact.get('size_bytes', 0)}",
                    f"- sha256: {artifact.get('sha256', '-')}",
                ]
            )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Smoke install",
            f"- status: {smoke.get('status', '-')}",
            f"- ran: {smoke.get('ran', False)}",
            f"- command: {smoke.get('command', '-')}",
            f"- return_code: {smoke.get('return_code', '-')}",
            "",
            "## Publish commands",
        ]
    )
    for key, value in commands.items():
        lines.append(f"- {key}: `{value}`")
    if outputs:
        lines.extend(
            [
                "",
                "## Artifact outputs",
                f"- json_path: {outputs.get('json_path', '-')}",
                f"- markdown_path: {outputs.get('markdown_path', '-')}",
                f"- asset_summary_path: {outputs.get('asset_summary_path', '-')}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_release_asset_summary_markdown(snapshot: dict[str, Any]) -> str:
    target = _mapping(snapshot, "target")
    summary = _mapping(snapshot, "summary")
    commands = _mapping(snapshot, "commands")
    artifacts = _list(snapshot.get("artifacts"))

    lines = [
        f"# Release asset dry-run for {target.get('tag', '-')}",
        "",
        f"- status: {summary.get('status', '-')}",
        f"- message: {summary.get('message', '-')}",
        "",
        "## Assets",
    ]
    for artifact in artifacts:
        lines.append(
            f"- `{artifact.get('name', '-')}` ({artifact.get('kind', '-')}, sha256={artifact.get('sha256', '-')})"
        )
    lines.extend(
        [
            "",
            "## Suggested next commands",
            f"1. `{commands.get('twine_check', '-')}`",
            f"2. `{commands.get('github_release_upload', '-')}`",
            f"3. `{commands.get('testpypi_upload', '-')}`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_release_asset_text(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot, "summary")
    target = _mapping(snapshot, "target")
    smoke = _mapping(snapshot, "smoke_install")
    lines = [
        "Release assets dry-run:",
        f"- status: {summary.get('status', '-')}",
        f"- message: {summary.get('message', '-')}",
        f"- target: {target.get('tag', '-')}",
        f"- artifact_count: {summary.get('artifact_count', 0)}",
        f"- smoke_install: {smoke.get('status', '-')}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _run_build(repo_root: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["uv", "build"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ran": True,
        "status": "ok" if completed.returncode == 0 else "error",
        "command": "uv build",
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _collect_dist_artifacts(
    *,
    dist_dir: Path,
    target_version: str,
) -> list[dict[str, Any]]:
    if not dist_dir.exists():
        return []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(item for item in dist_dir.iterdir() if item.is_file()):
        if path.name.startswith("."):
            continue
        kind = _artifact_kind(path)
        if kind == "other":
            continue
        version = _artifact_version(path.name)
        artifacts.append(
            {
                "name": path.name,
                "path": str(path),
                "kind": kind,
                "version": version,
                "version_matches_target": version == target_version,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return artifacts


def _artifact_kind(path: Path) -> str:
    if path.name.endswith(".whl"):
        return "wheel"
    if path.name.endswith(".tar.gz"):
        return "sdist"
    return "other"


def _artifact_version(name: str) -> str | None:
    if not name.startswith("reporepublic-"):
        return None
    remainder = name[len("reporepublic-") :]
    if remainder.endswith(".tar.gz"):
        return remainder[: -len(".tar.gz")]
    parts = remainder.split("-")
    return parts[0] if parts else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_smoke_install(
    *,
    repo_root: Path,
    dist_dir: Path,
    wheel_path: Path | None,
) -> dict[str, Any]:
    if wheel_path is None or not wheel_path.exists():
        return {
            "ran": False,
            "status": "error",
            "command": None,
            "return_code": None,
            "stdout": "",
            "stderr": "wheel artifact is missing",
        }
    with tempfile.TemporaryDirectory(prefix="reporepublic-release-assets-") as temp_dir:
        venv_dir = Path(temp_dir) / "venv"
        command = (
            f"{sys.executable} -m venv {venv_dir} && "
            f"{venv_dir / 'bin' / 'pip'} install {wheel_path} && "
            f"{venv_dir / 'bin' / 'republic'} --help"
        )
        completed = subprocess.run(
            [
                "bash",
                "-lc",
                command,
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    return {
        "ran": True,
        "status": "ok" if completed.returncode == 0 else "error",
        "command": command,
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _build_release_asset_commands(*, tag: str) -> dict[str, str]:
    return {
        "twine_check": "python -m twine check dist/*",
        "github_release_upload": f"gh release upload {tag} dist/* --clobber",
        "testpypi_upload": "python -m twine upload --repository testpypi dist/*",
        "pypi_upload": "python -m twine upload dist/*",
    }


def _build_release_asset_summary(
    *,
    artifacts: list[dict[str, Any]],
    build_result: dict[str, Any],
    smoke: dict[str, Any],
) -> dict[str, Any]:
    artifact_count = len(artifacts)
    wheel_count = sum(1 for item in artifacts if item["kind"] == "wheel")
    sdist_count = sum(1 for item in artifacts if item["kind"] == "sdist")
    mismatched = [item["name"] for item in artifacts if item["version_matches_target"] is False]

    errors: list[str] = []
    warnings: list[str] = []
    if build_result["status"] == "error":
        errors.append("uv build failed")
    if artifact_count == 0:
        errors.append("dist directory does not contain release artifacts")
    if wheel_count == 0:
        errors.append("wheel artifact is missing")
    if sdist_count == 0:
        errors.append("sdist artifact is missing")
    if smoke["status"] == "error":
        errors.append("smoke install failed")
    if mismatched:
        warnings.append("some dist artifacts do not match the target version")

    if errors:
        status = "issues"
        message = "Release asset dry-run has blocking issues."
    elif warnings:
        status = "attention"
        message = "Release asset dry-run needs follow-up before publish."
    else:
        status = "clean"
        message = "Release asset dry-run is ready for asset upload."
    return {
        "status": status,
        "message": message,
        "artifact_count": artifact_count,
        "wheel_count": wheel_count,
        "sdist_count": sdist_count,
        "version_mismatch_count": len(mismatched),
        "warning_count": len(warnings),
        "error_count": len(errors),
        "warnings": warnings,
        "errors": errors,
    }


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
