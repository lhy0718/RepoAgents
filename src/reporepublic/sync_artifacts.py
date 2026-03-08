from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

import yaml

from reporepublic.config import LoadedConfig


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
STAMP_ACTION_RE = re.compile(r"^(?P<staged_at>\d{8}T\d{6}\d*Z)-(?P<action>.+)$")
BUNDLE_ACTIONS = frozenset({"branch", "pr", "pr-body"})
BUNDLE_ACTION_ORDER = {"branch": 0, "pr": 1, "pr-body": 2}
NORMALIZED_SYNC_SCHEMA_VERSION = 1


class SyncArtifactLookupError(RuntimeError):
    """Raised when a staged sync artifact cannot be uniquely resolved."""


@dataclass(frozen=True, slots=True)
class SyncArtifact:
    state: str
    tracker: str
    issue_id: int | None
    action: str
    format: str
    path: Path
    relative_path: str
    staged_at: str | None
    metadata: dict[str, Any]
    normalized: dict[str, Any]
    body: str | None
    summary: str


@dataclass(frozen=True, slots=True)
class SyncApplyResult:
    tracker: str
    issue_id: int | None
    action: str
    state: str
    source_path: Path
    archived_path: Path
    manifest_path: Path
    effect: str


SyncEffectHandler = Callable[[LoadedConfig, SyncArtifact], str]
SyncBundleResolver = Callable[[LoadedConfig, SyncArtifact], list[SyncArtifact]]


@dataclass(frozen=True, slots=True)
class SyncApplyContext:
    entry_key: str
    group_key: str
    group_size: int
    group_index: int
    group_actions: tuple[str, ...]
    related_entry_keys: tuple[str, ...]
    related_source_paths: tuple[str, ...]


class SyncActionRegistry:
    def __init__(self) -> None:
        self._apply_handlers: dict[tuple[str, str], SyncEffectHandler] = {}
        self._bundle_resolvers: dict[str, SyncBundleResolver] = {}

    def register_apply_handler(self, tracker: str, action: str, handler: SyncEffectHandler) -> None:
        self._apply_handlers[(self._normalize_name(tracker), self._normalize_name(action))] = handler

    def register_bundle_resolver(self, tracker: str, resolver: SyncBundleResolver) -> None:
        self._bundle_resolvers[self._normalize_name(tracker)] = resolver

    def apply_effect(self, loaded: LoadedConfig, artifact: SyncArtifact) -> str:
        tracker_name = self._normalize_name(artifact.tracker)
        action_name = self._normalize_name(artifact.action)
        handler = self._apply_handlers.get((tracker_name, action_name))
        if handler is None:
            handler = self._apply_handlers.get((tracker_name, "*"))
        if handler is None:
            raise SyncArtifactLookupError(
                f"Sync apply is not implemented for tracker '{artifact.tracker}' action '{artifact.action}'."
            )
        return handler(loaded, artifact)

    def resolve_bundle(self, loaded: LoadedConfig, artifact: SyncArtifact) -> list[SyncArtifact]:
        if artifact.action not in BUNDLE_ACTIONS:
            return [artifact]
        resolver = self._bundle_resolvers.get(self._normalize_name(artifact.tracker))
        if resolver is None:
            return [artifact]
        return resolver(loaded, artifact)

    def _normalize_name(self, value: str) -> str:
        return value.strip().lower().replace("_", "-")


def _default_sync_action_registry() -> SyncActionRegistry:
    registry = SyncActionRegistry()
    for tracker in ("local-markdown", "local-file"):
        registry.register_bundle_resolver(tracker, _resolve_related_handoff_bundle)
    registry.register_apply_handler("local-markdown", "comment", _apply_local_markdown_comment_effect)
    registry.register_apply_handler("local-markdown", "labels", _apply_local_markdown_labels_effect)
    registry.register_apply_handler("local-markdown", "*", _archive_only_sync_effect)
    registry.register_apply_handler("local-file", "comment", _apply_local_file_comment_effect)
    registry.register_apply_handler("local-file", "labels", _apply_local_file_labels_effect)
    registry.register_apply_handler("local-file", "*", _archive_only_sync_effect)
    return registry


def list_sync_artifacts(
    loaded: LoadedConfig,
    *,
    issue_id: int | None = None,
    tracker: str | None = None,
    action: str | None = None,
    scope: str = "pending",
) -> list[SyncArtifact]:
    tracker_filter = _normalize_tracker_filter(tracker)
    action_filter = _normalize_action_filter(action)
    artifacts: list[SyncArtifact] = []

    for state, root in _iter_sync_roots(loaded, scope):
        if not root.exists():
            continue
        for tracker_root in sorted(root.iterdir()):
            if not tracker_root.is_dir():
                continue
            tracker_name = tracker_root.name
            if tracker_filter and tracker_name != tracker_filter:
                continue
            for issue_root in sorted(tracker_root.glob("issue-*")):
                if not issue_root.is_dir():
                    continue
                parsed_issue_id = _parse_issue_root_id(issue_root.name)
                if issue_id is not None and parsed_issue_id != issue_id:
                    continue
                for artifact_path in sorted(issue_root.iterdir(), reverse=True):
                    if not artifact_path.is_file():
                        continue
                    if artifact_path.name == "manifest.json":
                        continue
                    artifact = parse_sync_artifact(loaded, artifact_path, state=state)
                    if action_filter and artifact.action != action_filter:
                        continue
                    artifacts.append(artifact)
    return artifacts


def resolve_sync_artifact(
    loaded: LoadedConfig,
    artifact_ref: str,
    *,
    scope: str = "all",
) -> SyncArtifact:
    candidate = Path(artifact_ref)
    if candidate.is_absolute():
        if candidate.exists():
            return parse_sync_artifact(loaded, candidate, state=_detect_sync_state(loaded, candidate))
        raise SyncArtifactLookupError(f"Staged sync artifact not found: {candidate}")

    for state, root in _iter_sync_roots(loaded, scope):
        direct = (root / candidate).resolve()
        if direct.exists():
            return parse_sync_artifact(loaded, direct, state=state)

    matches = [
        artifact
        for artifact in list_sync_artifacts(loaded, scope=scope)
        if artifact.relative_path == artifact_ref or artifact.path.name == artifact_ref
    ]
    if not matches:
        raise SyncArtifactLookupError(
            f"Could not resolve staged sync artifact '{artifact_ref}' under {loaded.sync_dir} or {loaded.sync_applied_dir}."
        )
    if len(matches) > 1:
        joined = ", ".join(match.relative_path for match in matches[:5])
        raise SyncArtifactLookupError(
            f"Artifact reference '{artifact_ref}' is ambiguous. Matching paths: {joined}"
        )
    return matches[0]


def parse_sync_artifact(loaded: LoadedConfig, artifact_path: Path, *, state: str | None = None) -> SyncArtifact:
    resolved_path = artifact_path.resolve()
    resolved_state = state or _detect_sync_state(loaded, resolved_path)
    root = loaded.sync_dir.resolve() if resolved_state == "pending" else loaded.sync_applied_dir.resolve()
    try:
        relative_path = resolved_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise SyncArtifactLookupError(
            f"Staged sync artifact {artifact_path} is outside the expected sync root for state={resolved_state}."
        ) from exc

    tracker = resolved_path.parents[1].name if len(resolved_path.parents) >= 2 else "unknown"
    issue_id = _parse_issue_root_id(resolved_path.parent.name)
    staged_at, action = _parse_staged_name(resolved_path)

    metadata: dict[str, Any] = {}
    body: str | None = None
    artifact_format = _infer_format(resolved_path)

    if artifact_format == "json":
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            metadata = payload
        else:
            metadata = {"payload": payload}
        staged_at = str(metadata.get("staged_at") or staged_at or "")
    elif artifact_format == "markdown":
        text = resolved_path.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if match:
            parsed = yaml.safe_load(match.group(1)) or {}
            if isinstance(parsed, dict):
                metadata = parsed
            body = text[match.end():].strip()
            staged_at = str(metadata.get("staged_at") or staged_at or "")
        else:
            body = text.strip()
    else:
        body = resolved_path.read_text(encoding="utf-8").strip()

    normalized = _build_normalized_sync_metadata(
        loaded=loaded,
        tracker=tracker,
        issue_id=issue_id,
        action=action,
        relative_path=relative_path,
        metadata=metadata,
        staged_at=staged_at or None,
    )

    return SyncArtifact(
        state=resolved_state,
        tracker=tracker,
        issue_id=issue_id,
        action=action,
        format=artifact_format,
        path=resolved_path,
        relative_path=relative_path,
        staged_at=staged_at or None,
        metadata=metadata,
        normalized=normalized,
        body=body or None,
        summary=_build_summary(action=action, metadata=metadata, body=body),
    )


def apply_sync_artifact(
    loaded: LoadedConfig,
    artifact: SyncArtifact,
    *,
    keep_source: bool = False,
    registry: SyncActionRegistry | None = None,
    apply_context: SyncApplyContext | None = None,
) -> SyncApplyResult:
    if artifact.state != "pending":
        raise SyncArtifactLookupError(f"Only pending sync artifacts can be applied. Received state={artifact.state}.")
    resolved_registry = registry or DEFAULT_SYNC_ACTION_REGISTRY
    effect = resolved_registry.apply_effect(loaded, artifact)
    archived_path = _archive_sync_artifact(loaded, artifact, keep_source=keep_source)
    context = apply_context or _default_apply_context(artifact)
    manifest_path = _update_applied_manifest(
        loaded,
        artifact,
        archived_path=archived_path,
        effect=effect,
        apply_context=context,
    )
    return SyncApplyResult(
        tracker=artifact.tracker,
        issue_id=artifact.issue_id,
        action=artifact.action,
        state="applied",
        source_path=artifact.path,
        archived_path=archived_path,
        manifest_path=manifest_path,
        effect=effect,
    )


def resolve_sync_bundle(
    loaded: LoadedConfig,
    artifact: SyncArtifact,
    *,
    registry: SyncActionRegistry | None = None,
) -> list[SyncArtifact]:
    resolved_registry = registry or DEFAULT_SYNC_ACTION_REGISTRY
    return resolved_registry.resolve_bundle(loaded, artifact)


def _resolve_related_handoff_bundle(loaded: LoadedConfig, artifact: SyncArtifact) -> list[SyncArtifact]:
    pending_artifacts = list_sync_artifacts(
        loaded,
        issue_id=artifact.issue_id,
        tracker=artifact.tracker,
        scope="pending",
    )
    selected: dict[Path, SyncArtifact] = {artifact.path: artifact}
    bundle_key = _coerce_text(artifact.normalized.get("bundle_key"))

    branch_artifact: SyncArtifact | None = None
    pr_artifact: SyncArtifact | None = None
    pr_body_artifact: SyncArtifact | None = None

    if artifact.action == "branch":
        branch_artifact = artifact
        branch_name = _extract_branch_name(artifact)
        if branch_name:
            pr_artifact = _find_matching_pr_artifact(
                pending_artifacts,
                head_branch=branch_name,
                bundle_key=bundle_key,
            )
            if pr_artifact is not None:
                pr_body_artifact = _find_matching_pr_body_artifact(
                    pending_artifacts,
                    pr_artifact,
                    bundle_key=bundle_key,
                )
            if pr_body_artifact is None:
                pr_body_artifact = _find_matching_pr_body_artifact(
                    pending_artifacts,
                    None,
                    head_branch=branch_name,
                    bundle_key=bundle_key,
                )
    elif artifact.action == "pr":
        pr_artifact = artifact
        branch_name = _extract_branch_name(artifact)
        if branch_name:
            branch_artifact = _find_matching_branch_artifact(pending_artifacts, branch_name)
        pr_body_artifact = _find_matching_pr_body_artifact(
            pending_artifacts,
            pr_artifact,
            bundle_key=bundle_key,
        )
    elif artifact.action == "pr-body":
        pr_body_artifact = artifact
        metadata_path = _coerce_path(_extract_link_target(artifact, "metadata_artifact") or artifact.metadata.get("metadata_path"))
        branch_name = _extract_branch_name(artifact)
        pr_artifact = _find_matching_pr_artifact(
            pending_artifacts,
            metadata_path=metadata_path,
            head_branch=branch_name,
            title=_coerce_text(artifact.metadata.get("title")),
            bundle_key=bundle_key,
        )
        if branch_name:
            branch_artifact = _find_matching_branch_artifact(pending_artifacts, branch_name)

    for candidate in [branch_artifact, pr_artifact, pr_body_artifact]:
        if candidate is not None:
            selected[candidate.path] = candidate

    return sorted(
        selected.values(),
        key=lambda item: (
            BUNDLE_ACTION_ORDER.get(item.action, 99),
            item.staged_at or "",
            item.path.name,
        ),
    )


def apply_sync_bundle(
    loaded: LoadedConfig,
    artifact: SyncArtifact,
    *,
    keep_source: bool = False,
    registry: SyncActionRegistry | None = None,
) -> list[SyncApplyResult]:
    results: list[SyncApplyResult] = []
    bundle = resolve_sync_bundle(loaded, artifact, registry=registry)
    contexts = _build_bundle_apply_contexts(bundle)
    for candidate, context in zip(bundle, contexts, strict=True):
        results.append(
            apply_sync_artifact(
                loaded,
                candidate,
                keep_source=keep_source,
                registry=registry,
                apply_context=context,
            )
        )
    return results


def _infer_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".md":
        return "markdown"
    return suffix.removeprefix(".") or "unknown"


def _parse_staged_name(path: Path) -> tuple[str | None, str]:
    match = STAMP_ACTION_RE.match(path.stem)
    if not match:
        return None, path.stem
    return match.group("staged_at"), match.group("action")


def _parse_issue_root_id(name: str) -> int | None:
    if not name.startswith("issue-"):
        return None
    suffix = name.removeprefix("issue-")
    return int(suffix) if suffix.isdigit() else None


def _normalize_tracker_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "-")
    return normalized or None


def _normalize_action_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "-")
    return normalized or None


def _build_summary(
    *,
    action: str,
    metadata: dict[str, Any],
    body: str | None,
) -> str:
    if body:
        first_line = next(
            (
                line.strip()
                for line in body.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ),
            "",
        )
        if first_line:
            return first_line[:120]
    if "title" in metadata:
        return f"title={metadata['title']}"
    if "branch_name" in metadata:
        return f"branch={metadata['branch_name']}"
    if "labels" in metadata and isinstance(metadata["labels"], list):
        return "labels=" + ", ".join(str(label) for label in metadata["labels"])
    return action


def _build_normalized_sync_metadata(
    *,
    loaded: LoadedConfig,
    tracker: str,
    issue_id: int | None,
    action: str,
    relative_path: str,
    metadata: dict[str, Any],
    staged_at: str | None,
) -> dict[str, Any]:
    head_ref = _coerce_text(metadata.get("branch_name")) or _coerce_text(metadata.get("head_branch"))
    base_ref = _coerce_text(metadata.get("base_branch"))
    title = _coerce_text(metadata.get("title"))
    labels = _normalize_label_list(metadata.get("labels"))
    metadata_artifact = _normalize_link_target(loaded, metadata.get("metadata_path"))
    issue_key = f"issue:{issue_id}" if issue_id is not None else None
    bundle_key = _build_bundle_key(issue_id=issue_id, head_ref=head_ref, title=title)

    links: dict[str, str] = {"self": relative_path}
    if metadata_artifact:
        links["metadata_artifact"] = metadata_artifact

    refs: dict[str, str] = {}
    if head_ref:
        refs["head"] = head_ref
    if base_ref:
        refs["base"] = base_ref

    normalized = {
        "schema_version": NORMALIZED_SYNC_SCHEMA_VERSION,
        "artifact_role": _artifact_role(action),
        "issue_key": issue_key,
        "bundle_key": bundle_key,
        "links": links,
        "refs": refs,
    }
    if title:
        normalized["title"] = title
    if labels:
        normalized["labels"] = labels
    return normalized


def _iter_sync_roots(loaded: LoadedConfig, scope: str) -> list[tuple[str, Path]]:
    normalized = scope.strip().lower()
    if normalized == "pending":
        return [("pending", loaded.sync_dir)]
    if normalized == "applied":
        return [("applied", loaded.sync_applied_dir)]
    if normalized == "all":
        return [("pending", loaded.sync_dir), ("applied", loaded.sync_applied_dir)]
    raise SyncArtifactLookupError(f"Unsupported sync scope '{scope}'. Expected one of: pending, applied, all.")


def _detect_sync_state(loaded: LoadedConfig, path: Path) -> str:
    resolved = path.resolve()
    if _is_relative_to(resolved, loaded.sync_dir.resolve()):
        return "pending"
    if _is_relative_to(resolved, loaded.sync_applied_dir.resolve()):
        return "applied"
    raise SyncArtifactLookupError(
        f"Sync artifact {path} is outside {loaded.sync_dir} and {loaded.sync_applied_dir}."
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _apply_local_markdown_comment_effect(loaded: LoadedConfig, artifact: SyncArtifact) -> str:
    issue_file = _find_local_markdown_issue_file(loaded, artifact.issue_id)
    metadata, body = _read_local_markdown_issue_file(issue_file)
    comments = metadata.get("comments", [])
    if not isinstance(comments, list):
        comments = []
    comments.append(
        {
            "author": "reporepublic",
            "body": artifact.body or "",
            "created_at": artifact.staged_at,
        }
    )
    metadata["comments"] = comments
    _write_local_markdown_issue_file(issue_file, metadata, body)
    return f"Appended staged comment to {issue_file}."


def _apply_local_markdown_labels_effect(loaded: LoadedConfig, artifact: SyncArtifact) -> str:
    issue_file = _find_local_markdown_issue_file(loaded, artifact.issue_id)
    metadata, body = _read_local_markdown_issue_file(issue_file)
    existing = metadata.get("labels", [])
    if isinstance(existing, str):
        existing = [existing]
    if not isinstance(existing, list):
        existing = []
    staged_labels = artifact.metadata.get("labels", [])
    if isinstance(staged_labels, str):
        staged_labels = [staged_labels]
    merged: list[str] = []
    for label in [*existing, *staged_labels]:
        rendered = str(label).strip()
        if rendered and rendered not in merged:
            merged.append(rendered)
    metadata["labels"] = merged
    _write_local_markdown_issue_file(issue_file, metadata, body)
    return f"Merged staged labels into {issue_file}."


def _apply_local_file_comment_effect(loaded: LoadedConfig, artifact: SyncArtifact) -> str:
    issue_path = _local_file_issue_path(loaded)
    payload, issues = _read_local_file_issue_payload(issue_path)
    issue_entry = _find_local_file_issue_entry(issues, artifact.issue_id)
    comments = issue_entry.get("comments", [])
    if not isinstance(comments, list):
        comments = []
    comments.append(
        {
            "author": "reporepublic",
            "body": artifact.body or "",
            "created_at": artifact.staged_at,
        }
    )
    issue_entry["comments"] = comments
    _write_local_file_issue_payload(issue_path, payload, issues)
    return f"Appended staged comment to {issue_path}."


def _apply_local_file_labels_effect(loaded: LoadedConfig, artifact: SyncArtifact) -> str:
    issue_path = _local_file_issue_path(loaded)
    payload, issues = _read_local_file_issue_payload(issue_path)
    issue_entry = _find_local_file_issue_entry(issues, artifact.issue_id)
    existing = issue_entry.get("labels", [])
    if isinstance(existing, str):
        existing = [existing]
    if not isinstance(existing, list):
        existing = []
    staged_labels = artifact.metadata.get("labels", [])
    if isinstance(staged_labels, str):
        staged_labels = [staged_labels]
    merged: list[str] = []
    for label in [*existing, *staged_labels]:
        rendered = str(label).strip()
        if rendered and rendered not in merged:
            merged.append(rendered)
    issue_entry["labels"] = merged
    _write_local_file_issue_payload(issue_path, payload, issues)
    return f"Merged staged labels into {issue_path}."


def _archive_only_sync_effect(_loaded: LoadedConfig, artifact: SyncArtifact) -> str:
    return f"Archived {artifact.action} handoff artifact for offline processing."


def _find_local_markdown_issue_file(loaded: LoadedConfig, issue_id: int | None) -> Path:
    if issue_id is None:
        raise SyncArtifactLookupError("local_markdown sync apply requires an issue-scoped artifact.")
    tracker_path = loaded.resolve(loaded.data.tracker.path or "issues")
    if loaded.data.tracker.kind.value != "local_markdown":
        raise SyncArtifactLookupError(
            "local_markdown sync apply requires the current repo config to use tracker.kind=local_markdown."
        )
    for file_path in sorted(tracker_path.glob("*.md")):
        metadata, _ = _read_local_markdown_issue_file(file_path)
        candidates = {
            _coerce_issue_number(metadata.get("id")),
            _coerce_issue_number(metadata.get("number")),
            _infer_issue_number(file_path),
        }
        if issue_id in candidates:
            return file_path
    raise SyncArtifactLookupError(f"Could not find local_markdown issue file for issue #{issue_id} in {tracker_path}.")


def _local_file_issue_path(loaded: LoadedConfig) -> Path:
    if loaded.data.tracker.kind.value != "local_file":
        raise SyncArtifactLookupError(
            "local_file sync apply requires the current repo config to use tracker.kind=local_file."
        )
    return loaded.resolve(loaded.data.tracker.path or "issues.json")


def _read_local_file_issue_payload(path: Path) -> tuple[dict[str, Any] | list[dict[str, Any]], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        issues = payload.get("issues", [])
        if not isinstance(issues, list):
            raise SyncArtifactLookupError(f"Local issue file at {path} must contain an 'issues' array.")
        normalized = [item for item in issues if isinstance(item, dict)]
        if len(normalized) != len(issues):
            raise SyncArtifactLookupError(f"Each issue entry in {path} must be a JSON object.")
        return payload, normalized
    if isinstance(payload, list):
        normalized = [item for item in payload if isinstance(item, dict)]
        if len(normalized) != len(payload):
            raise SyncArtifactLookupError(f"Each issue entry in {path} must be a JSON object.")
        return payload, normalized
    raise SyncArtifactLookupError(f"Local issue file at {path} must contain a JSON array or an object with an 'issues' array.")


def _find_local_file_issue_entry(issues: list[dict[str, Any]], issue_id: int | None) -> dict[str, Any]:
    if issue_id is None:
        raise SyncArtifactLookupError("local_file sync apply requires an issue-scoped artifact.")
    for issue in issues:
        candidates = {_coerce_issue_number(issue.get("id")), _coerce_issue_number(issue.get("number"))}
        if issue_id in candidates:
            return issue
    raise SyncArtifactLookupError(f"Could not find local_file issue entry for issue #{issue_id}.")


def _write_local_file_issue_payload(
    path: Path,
    payload: dict[str, Any] | list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    if isinstance(payload, dict):
        payload["issues"] = issues
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return
    path.write_text(json.dumps(issues, indent=2, sort_keys=True), encoding="utf-8")


def _read_local_markdown_issue_file(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    metadata: dict[str, Any] = {}
    body = text
    match = FRONTMATTER_RE.match(text)
    if match:
        parsed = yaml.safe_load(match.group(1)) or {}
        if isinstance(parsed, dict):
            metadata = dict(parsed)
        body = text[match.end():]
    lines = body.splitlines()
    if "title" not in metadata:
        for index, line in enumerate(lines):
            if line.startswith("# "):
                metadata["title"] = line[2:].strip()
                body = "\n".join(lines[index + 1 :]).lstrip()
                break
    return metadata, body.strip()


def _write_local_markdown_issue_file(path: Path, metadata: dict[str, Any], body: str) -> None:
    rendered_metadata = {key: value for key, value in metadata.items() if value not in (None, [], "")}
    frontmatter = yaml.safe_dump(rendered_metadata, sort_keys=False).strip()
    rendered_body = body.rstrip()
    if rendered_body:
        path.write_text(f"---\n{frontmatter}\n---\n\n{rendered_body}\n", encoding="utf-8")
        return
    path.write_text(f"---\n{frontmatter}\n---\n", encoding="utf-8")


def _coerce_issue_number(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _infer_issue_number(path: Path) -> int | None:
    match = re.match(r"^(\d+)", path.stem)
    if not match:
        return None
    return int(match.group(1))


def _extract_branch_name(artifact: SyncArtifact) -> str | None:
    refs = artifact.normalized.get("refs", {})
    if isinstance(refs, dict):
        normalized_head = _coerce_text(refs.get("head"))
        if normalized_head:
            return normalized_head
    return _coerce_text(artifact.metadata.get("branch_name")) or _coerce_text(artifact.metadata.get("head_branch"))


def _find_matching_branch_artifact(artifacts: list[SyncArtifact], branch_name: str) -> SyncArtifact | None:
    candidates = [
        artifact
        for artifact in artifacts
        if artifact.action == "branch" and _extract_branch_name(artifact) == branch_name
    ]
    return _latest_sync_artifact(candidates)


def _find_matching_pr_artifact(
    artifacts: list[SyncArtifact],
    *,
    metadata_path: Path | None = None,
    head_branch: str | None = None,
    title: str | None = None,
    bundle_key: str | None = None,
) -> SyncArtifact | None:
    candidates = [artifact for artifact in artifacts if artifact.action == "pr"]
    if bundle_key:
        bundled = [artifact for artifact in candidates if _coerce_text(artifact.normalized.get("bundle_key")) == bundle_key]
        if bundled:
            return _latest_sync_artifact(bundled)
    if metadata_path is not None:
        exact_path = metadata_path.resolve()
        for artifact in candidates:
            if artifact.path.resolve() == exact_path:
                return artifact
    if head_branch:
        narrowed = [artifact for artifact in candidates if _extract_branch_name(artifact) == head_branch]
        if title:
            titled = [artifact for artifact in narrowed if _coerce_text(artifact.metadata.get("title")) == title]
            return _latest_sync_artifact(titled) or _latest_sync_artifact(narrowed)
        return _latest_sync_artifact(narrowed)
    if title:
        titled = [artifact for artifact in candidates if _coerce_text(artifact.metadata.get("title")) == title]
        return _latest_sync_artifact(titled)
    return None


def _find_matching_pr_body_artifact(
    artifacts: list[SyncArtifact],
    pr_artifact: SyncArtifact | None,
    *,
    head_branch: str | None = None,
    bundle_key: str | None = None,
) -> SyncArtifact | None:
    candidates = [artifact for artifact in artifacts if artifact.action == "pr-body"]
    if bundle_key:
        bundled = [artifact for artifact in candidates if _coerce_text(artifact.normalized.get("bundle_key")) == bundle_key]
        if bundled:
            return _latest_sync_artifact(bundled)
    if pr_artifact is not None:
        exact_path = pr_artifact.path.resolve()
        exact = [
            artifact
            for artifact in candidates
            if _coerce_path(_extract_link_target(artifact, "metadata_artifact")) == exact_path
        ]
        if exact:
            return _latest_sync_artifact(exact)
        branch_name = _extract_branch_name(pr_artifact)
        title = _coerce_text(pr_artifact.metadata.get("title"))
        fallback = [
            artifact
            for artifact in candidates
            if (
                (branch_name is None or _extract_branch_name(artifact) == branch_name)
                and (title is None or _coerce_text(artifact.metadata.get("title")) == title)
            )
        ]
        return _latest_sync_artifact(fallback)
    if head_branch:
        fallback = [artifact for artifact in candidates if _extract_branch_name(artifact) == head_branch]
        return _latest_sync_artifact(fallback)
    return None


def _latest_sync_artifact(artifacts: list[SyncArtifact]) -> SyncArtifact | None:
    if not artifacts:
        return None
    return sorted(
        artifacts,
        key=lambda item: (item.staged_at or "", item.path.name),
    )[-1]


def _coerce_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).resolve()


def _coerce_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _artifact_role(action: str) -> str:
    return {
        "comment": "comment-proposal",
        "labels": "label-proposal",
        "branch": "branch-proposal",
        "pr": "pr-proposal",
        "pr-body": "pr-body-proposal",
    }.get(action, f"{action}-proposal")


def _build_bundle_key(
    *,
    issue_id: int | None,
    head_ref: str | None,
    title: str | None,
) -> str | None:
    if issue_id is None:
        return None
    if head_ref:
        return f"issue:{issue_id}|head:{head_ref}"
    if title:
        return f"issue:{issue_id}|title:{title}"
    return f"issue:{issue_id}"


def _normalize_link_target(loaded: LoadedConfig, value: object) -> str | None:
    raw = _coerce_text(value)
    if raw is None:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        return raw
    for root in (loaded.sync_dir.resolve(), loaded.sync_applied_dir.resolve()):
        if _is_relative_to(candidate.resolve(), root):
            return candidate.resolve().relative_to(root).as_posix()
    return raw


def _extract_link_target(artifact: SyncArtifact, relation: str) -> str | None:
    links = artifact.normalized.get("links", {})
    if isinstance(links, dict):
        target = _coerce_text(links.get(relation))
        if target:
            return target
    return None


def _normalize_label_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        rendered = str(item).strip()
        if rendered:
            normalized.append(rendered)
    return normalized


def _build_entry_key(artifact: SyncArtifact) -> str:
    return f"{artifact.tracker}:{artifact.relative_path}"


def _archive_sync_artifact(loaded: LoadedConfig, artifact: SyncArtifact, *, keep_source: bool) -> Path:
    issue_root = f"issue-{artifact.issue_id}" if artifact.issue_id is not None else "issue-unknown"
    archive_dir = loaded.sync_applied_dir / artifact.tracker / issue_root
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / artifact.path.name
    if keep_source:
        target.write_bytes(artifact.path.read_bytes())
        return target
    artifact.path.replace(target)
    return target


def _default_apply_context(artifact: SyncArtifact) -> SyncApplyContext:
    entry_key = _build_entry_key(artifact)
    group_key = _coerce_text(artifact.normalized.get("bundle_key")) or entry_key
    return SyncApplyContext(
        entry_key=entry_key,
        group_key=group_key,
        group_size=1,
        group_index=0,
        group_actions=(artifact.action,),
        related_entry_keys=(entry_key,),
        related_source_paths=(artifact.relative_path,),
    )


def _build_bundle_apply_contexts(bundle: list[SyncArtifact]) -> list[SyncApplyContext]:
    if not bundle:
        return []
    entry_keys = tuple(_build_entry_key(artifact) for artifact in bundle)
    source_paths = tuple(artifact.relative_path for artifact in bundle)
    group_actions = tuple(artifact.action for artifact in bundle)
    default_group_key = _coerce_text(bundle[0].normalized.get("bundle_key")) or entry_keys[0]
    contexts: list[SyncApplyContext] = []
    for index, artifact in enumerate(bundle):
        contexts.append(
            SyncApplyContext(
                entry_key=entry_keys[index],
                group_key=_coerce_text(artifact.normalized.get("bundle_key")) or default_group_key,
                group_size=len(bundle),
                group_index=index,
                group_actions=group_actions,
                related_entry_keys=entry_keys,
                related_source_paths=source_paths,
            )
        )
    return contexts


def _update_applied_manifest(
    loaded: LoadedConfig,
    artifact: SyncArtifact,
    *,
    archived_path: Path,
    effect: str,
    apply_context: SyncApplyContext,
) -> Path:
    issue_root = f"issue-{artifact.issue_id}" if artifact.issue_id is not None else "issue-unknown"
    manifest_path = loaded.sync_applied_dir / artifact.tracker / issue_root / "manifest.json"
    entries: list[dict[str, Any]] = []
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            entries = payload
    archived_relative_path = archived_path.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix()
    entries.append(
        {
            "entry_key": apply_context.entry_key,
            "tracker": artifact.tracker,
            "issue_id": artifact.issue_id,
            "action": artifact.action,
            "format": artifact.format,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "staged_at": artifact.staged_at,
            "summary": artifact.summary,
            "normalized": artifact.normalized,
            "source_relative_path": artifact.relative_path,
            "archived_relative_path": archived_relative_path,
            "archived_path": str(archived_path),
            "effect": effect,
            "handoff": {
                "group_key": apply_context.group_key,
                "group_size": apply_context.group_size,
                "group_index": apply_context.group_index,
                "group_actions": list(apply_context.group_actions),
                "related_entry_keys": list(apply_context.related_entry_keys),
                "related_source_paths": list(apply_context.related_source_paths),
            },
        }
    )
    manifest_path.write_text(json.dumps(entries, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


DEFAULT_SYNC_ACTION_REGISTRY = _default_sync_action_registry()
