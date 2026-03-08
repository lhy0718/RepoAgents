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
from reporepublic.utils.files import write_json_file


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


@dataclass(frozen=True, slots=True)
class AppliedSyncManifestFinding:
    code: str
    message: str
    entry_key: str | None = None
    path: str | None = None


@dataclass(frozen=True, slots=True)
class AppliedSyncManifestReport:
    tracker: str
    issue_id: int | None
    issue_root: Path
    manifest_path: Path
    manifest_exists: bool
    archive_files: tuple[str, ...]
    findings: tuple[AppliedSyncManifestFinding, ...]
    manifest_entry_count: int
    referenced_archive_count: int


@dataclass(frozen=True, slots=True)
class AppliedSyncManifestRepairResult:
    tracker: str
    issue_id: int | None
    issue_root: Path
    manifest_path: Path
    changed: bool
    dry_run: bool
    manifest_entry_count_before: int
    manifest_entry_count_after: int
    findings_before: int
    findings_after: int
    dropped_entries: int
    adopted_archives: int
    normalized_entries: int


@dataclass(frozen=True, slots=True)
class SyncAppliedRetentionGroup:
    group_key: str
    tracker: str
    issue_id: int | None
    status: str
    actions: tuple[str, ...]
    archive_paths: tuple[str, ...]
    total_bytes: int
    archive_file_count: int
    newest_at: str | None
    oldest_at: str | None
    newest_age_seconds: int | None
    oldest_age_seconds: int | None


@dataclass(frozen=True, slots=True)
class SyncAppliedRetentionIssueSummary:
    tracker: str
    issue_id: int | None
    issue_root: Path
    manifest_path: Path
    status: str
    keep_groups_limit: int
    integrity_findings: int
    finding_codes: tuple[str, ...]
    total_groups: int
    kept_groups: int
    prunable_groups: int
    total_bytes: int
    kept_bytes: int
    prunable_bytes: int
    newest_group_age_seconds: int | None
    oldest_group_age_seconds: int | None
    oldest_prunable_group_age_seconds: int | None
    groups: tuple[SyncAppliedRetentionGroup, ...]


@dataclass(frozen=True, slots=True)
class SyncAppliedRetentionSnapshot:
    keep_groups_per_issue: int
    total_issues: int
    eligible_issues: int
    stable_issues: int
    prunable_issues: int
    repair_needed_issues: int
    total_groups: int
    kept_groups: int
    prunable_groups: int
    total_bytes: int
    kept_bytes: int
    prunable_bytes: int
    entries: tuple[SyncAppliedRetentionIssueSummary, ...]


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


def inspect_applied_sync_manifests(
    loaded: LoadedConfig,
    *,
    issue_id: int | None = None,
    tracker: str | None = None,
) -> list[AppliedSyncManifestReport]:
    reports: list[AppliedSyncManifestReport] = []
    for issue_root in _iter_applied_issue_roots(loaded, issue_id=issue_id, tracker=tracker):
        reports.append(_inspect_applied_sync_issue_root(loaded, issue_root))
    return reports


def repair_applied_sync_manifests(
    loaded: LoadedConfig,
    *,
    issue_id: int | None = None,
    tracker: str | None = None,
    dry_run: bool = False,
) -> list[AppliedSyncManifestRepairResult]:
    results: list[AppliedSyncManifestRepairResult] = []
    for issue_root in _iter_applied_issue_roots(loaded, issue_id=issue_id, tracker=tracker):
        before_report = _inspect_applied_sync_issue_root(loaded, issue_root)
        raw_entries, _manifest_error = _load_manifest_payload(before_report.manifest_path)
        canonical_entries, repair_stats = _repair_issue_manifest_entries(loaded, issue_root, raw_entries)
        if not dry_run:
            if canonical_entries or before_report.manifest_exists:
                write_json_file(before_report.manifest_path, canonical_entries)
        after_report = (
            _inspect_repaired_issue_manifest(loaded, issue_root, canonical_entries)
            if dry_run
            else _inspect_applied_sync_issue_root(loaded, issue_root)
        )
        results.append(
            AppliedSyncManifestRepairResult(
                tracker=before_report.tracker,
                issue_id=before_report.issue_id,
                issue_root=issue_root,
                manifest_path=before_report.manifest_path,
                changed=before_report.findings != after_report.findings or before_report.manifest_entry_count != len(canonical_entries),
                dry_run=dry_run,
                manifest_entry_count_before=before_report.manifest_entry_count,
                manifest_entry_count_after=len(canonical_entries),
                findings_before=len(before_report.findings),
                findings_after=len(after_report.findings),
                dropped_entries=repair_stats["dropped_entries"],
                adopted_archives=repair_stats["adopted_archives"],
                normalized_entries=repair_stats["normalized_entries"],
            )
        )
    return results


def summarize_sync_applied_retention(
    loaded: LoadedConfig,
    *,
    keep_groups_per_issue: int | None = None,
    issue_id: int | None = None,
    tracker: str | None = None,
    limit: int | None = None,
) -> SyncAppliedRetentionSnapshot:
    resolved_keep_groups = keep_groups_per_issue or loaded.data.cleanup.sync_applied_keep_groups_per_issue
    issue_summaries: list[SyncAppliedRetentionIssueSummary] = []
    for issue_root in _iter_applied_issue_roots(loaded, issue_id=issue_id, tracker=tracker):
        summary = _summarize_sync_applied_issue_retention(
            loaded,
            issue_root=issue_root,
            keep_groups_per_issue=resolved_keep_groups,
        )
        if summary is not None:
            issue_summaries.append(summary)

    issue_summaries.sort(key=_retention_issue_sort_key)
    visible_entries = tuple(issue_summaries if limit is None else issue_summaries[:limit])
    stable_issues = sum(1 for entry in issue_summaries if entry.status == "stable")
    prunable_issues = sum(1 for entry in issue_summaries if entry.status == "prunable")
    repair_needed_issues = sum(1 for entry in issue_summaries if entry.status == "repair-needed")
    eligible_issues = stable_issues + prunable_issues
    return SyncAppliedRetentionSnapshot(
        keep_groups_per_issue=resolved_keep_groups,
        total_issues=len(issue_summaries),
        eligible_issues=eligible_issues,
        stable_issues=stable_issues,
        prunable_issues=prunable_issues,
        repair_needed_issues=repair_needed_issues,
        total_groups=sum(entry.total_groups for entry in issue_summaries),
        kept_groups=sum(entry.kept_groups for entry in issue_summaries),
        prunable_groups=sum(entry.prunable_groups for entry in issue_summaries),
        total_bytes=sum(entry.total_bytes for entry in issue_summaries),
        kept_bytes=sum(entry.kept_bytes for entry in issue_summaries),
        prunable_bytes=sum(entry.prunable_bytes for entry in issue_summaries),
        entries=visible_entries,
    )


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


def _iter_applied_issue_roots(
    loaded: LoadedConfig,
    *,
    issue_id: int | None,
    tracker: str | None,
) -> list[Path]:
    tracker_filter = _normalize_tracker_filter(tracker)
    issue_roots: list[Path] = []
    if not loaded.sync_applied_dir.exists():
        return issue_roots
    for tracker_root in sorted(loaded.sync_applied_dir.iterdir()):
        if not tracker_root.is_dir():
            continue
        if tracker_filter and tracker_root.name != tracker_filter:
            continue
        for issue_root in sorted(tracker_root.glob("issue-*")):
            if not issue_root.is_dir():
                continue
            parsed_issue_id = _parse_issue_root_id(issue_root.name)
            if issue_id is not None and parsed_issue_id != issue_id:
                continue
            issue_roots.append(issue_root)
    return issue_roots


def _inspect_applied_sync_issue_root(loaded: LoadedConfig, issue_root: Path) -> AppliedSyncManifestReport:
    manifest_path = issue_root / "manifest.json"
    archive_files = sorted(
        path.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix()
        for path in issue_root.iterdir()
        if path.is_file() and path.name != "manifest.json"
    )
    manifest_exists = manifest_path.exists()
    findings: list[AppliedSyncManifestFinding] = []
    raw_entries, manifest_error = _load_manifest_payload(manifest_path)

    if not manifest_exists and archive_files:
        findings.append(
            AppliedSyncManifestFinding(
                code="missing_manifest",
                message="Applied archive files exist but manifest.json is missing.",
                path=issue_root.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix(),
            )
        )
    if manifest_error == "invalid_json":
        findings.append(
            AppliedSyncManifestFinding(
                code="invalid_manifest_json",
                message="manifest.json is not valid JSON.",
                path=manifest_path.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix(),
            )
        )
    elif manifest_error == "invalid_format":
        findings.append(
            AppliedSyncManifestFinding(
                code="invalid_manifest_format",
                message="manifest.json must contain a JSON array of manifest entries.",
                path=manifest_path.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix(),
            )
        )

    referenced_archives: set[str] = set()
    entry_keys: dict[str, int] = {}
    archive_refs: dict[str, int] = {}
    valid_entries: list[dict[str, Any]] = []
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            findings.append(
                AppliedSyncManifestFinding(
                    code="invalid_entry_type",
                    message="Manifest entry is not a JSON object.",
                    path=manifest_path.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix(),
                )
            )
            continue
        archive_path = _resolve_applied_manifest_archive_path(loaded, entry)
        archived_relative_path = _resolve_applied_manifest_relative_path(loaded, entry)
        entry_key = _coerce_text(entry.get("entry_key"))
        if entry_key:
            if entry_key in entry_keys:
                findings.append(
                    AppliedSyncManifestFinding(
                        code="duplicate_entry_key",
                        message="Multiple manifest entries share the same entry_key.",
                        entry_key=entry_key,
                        path=archived_relative_path or _coerce_text(entry.get("archived_path")),
                    )
                )
            entry_keys[entry_key] = entry_keys.get(entry_key, 0) + 1
        if archive_path is None or archived_relative_path is None or not archive_path.exists():
            findings.append(
                AppliedSyncManifestFinding(
                    code="dangling_archive_reference",
                    message="Manifest entry points to an archived artifact that does not exist.",
                    entry_key=entry_key,
                    path=archived_relative_path or _coerce_text(entry.get("archived_path")),
                )
            )
            continue
        valid_entries.append(entry)
        referenced_archives.add(archived_relative_path)
        if archived_relative_path in archive_refs:
            findings.append(
                AppliedSyncManifestFinding(
                    code="duplicate_archive_reference",
                    message="Multiple manifest entries point at the same archived artifact.",
                    entry_key=entry_key,
                    path=archived_relative_path,
                )
            )
        archive_refs[archived_relative_path] = archive_refs.get(archived_relative_path, 0) + 1
        if _coerce_text(entry.get("archived_path")) != str(archive_path):
            findings.append(
                AppliedSyncManifestFinding(
                    code="mismatched_archived_path",
                    message="archived_path does not match the artifact currently stored under sync-applied.",
                    entry_key=entry_key,
                    path=archived_relative_path,
                )
            )
        if not _coerce_text(entry.get("archived_relative_path")):
            findings.append(
                AppliedSyncManifestFinding(
                    code="missing_archived_relative_path",
                    message="Manifest entry is missing archived_relative_path.",
                    entry_key=entry_key,
                    path=archived_relative_path,
                )
            )

    orphans = sorted(set(archive_files) - referenced_archives)
    for orphan in orphans:
        findings.append(
            AppliedSyncManifestFinding(
                code="orphan_archive_file",
                message="Archived artifact exists under sync-applied but is not referenced by manifest.json.",
                path=orphan,
            )
        )

    _append_group_integrity_findings(findings, valid_entries)

    return AppliedSyncManifestReport(
        tracker=issue_root.parent.name,
        issue_id=_parse_issue_root_id(issue_root.name),
        issue_root=issue_root,
        manifest_path=manifest_path,
        manifest_exists=manifest_exists,
        archive_files=tuple(archive_files),
        findings=tuple(findings),
        manifest_entry_count=len(raw_entries),
        referenced_archive_count=len(referenced_archives),
    )


def _summarize_sync_applied_issue_retention(
    loaded: LoadedConfig,
    *,
    issue_root: Path,
    keep_groups_per_issue: int,
) -> SyncAppliedRetentionIssueSummary | None:
    manifest_path = issue_root / "manifest.json"
    existing_files = sorted(
        path for path in issue_root.iterdir() if path.is_file() and path.name != "manifest.json"
    )
    if not manifest_path.exists() and not existing_files:
        return None

    report = _inspect_applied_sync_issue_root(loaded, issue_root)
    total_bytes = sum(path.stat().st_size for path in existing_files)
    finding_codes = tuple(sorted({finding.code for finding in report.findings}))
    if report.findings:
        return SyncAppliedRetentionIssueSummary(
            tracker=report.tracker,
            issue_id=report.issue_id,
            issue_root=issue_root,
            manifest_path=manifest_path,
            status="repair-needed",
            keep_groups_limit=keep_groups_per_issue,
            integrity_findings=len(report.findings),
            finding_codes=finding_codes,
            total_groups=0,
            kept_groups=0,
            prunable_groups=0,
            total_bytes=total_bytes,
            kept_bytes=0,
            prunable_bytes=0,
            newest_group_age_seconds=None,
            oldest_group_age_seconds=None,
            oldest_prunable_group_age_seconds=None,
            groups=(),
        )

    payload, manifest_error = _load_manifest_payload(manifest_path)
    if manifest_error is not None:
        return SyncAppliedRetentionIssueSummary(
            tracker=report.tracker,
            issue_id=report.issue_id,
            issue_root=issue_root,
            manifest_path=manifest_path,
            status="repair-needed",
            keep_groups_limit=keep_groups_per_issue,
            integrity_findings=1,
            finding_codes=(manifest_error,),
            total_groups=0,
            kept_groups=0,
            prunable_groups=0,
            total_bytes=total_bytes,
            kept_bytes=0,
            prunable_bytes=0,
            newest_group_age_seconds=None,
            oldest_group_age_seconds=None,
            oldest_prunable_group_age_seconds=None,
            groups=(),
        )

    groups = _build_sync_applied_retention_groups(
        loaded,
        issue_root=issue_root,
        entries=[entry for entry in payload if isinstance(entry, dict)],
        keep_groups_per_issue=keep_groups_per_issue,
    )
    if not groups and total_bytes == 0:
        return None

    kept_groups = sum(1 for group in groups if group.status == "kept")
    prunable_groups = sum(1 for group in groups if group.status == "prunable")
    kept_bytes = sum(group.total_bytes for group in groups if group.status == "kept")
    prunable_bytes = sum(group.total_bytes for group in groups if group.status == "prunable")
    newest_group_age_seconds = min(
        (group.newest_age_seconds for group in groups if group.newest_age_seconds is not None),
        default=None,
    )
    oldest_group_age_seconds = max(
        (group.oldest_age_seconds for group in groups if group.oldest_age_seconds is not None),
        default=None,
    )
    oldest_prunable_group_age_seconds = max(
        (
            group.oldest_age_seconds
            for group in groups
            if group.status == "prunable" and group.oldest_age_seconds is not None
        ),
        default=None,
    )
    return SyncAppliedRetentionIssueSummary(
        tracker=report.tracker,
        issue_id=report.issue_id,
        issue_root=issue_root,
        manifest_path=manifest_path,
        status="prunable" if prunable_groups else "stable",
        keep_groups_limit=keep_groups_per_issue,
        integrity_findings=0,
        finding_codes=(),
        total_groups=len(groups),
        kept_groups=kept_groups,
        prunable_groups=prunable_groups,
        total_bytes=total_bytes,
        kept_bytes=kept_bytes,
        prunable_bytes=prunable_bytes,
        newest_group_age_seconds=newest_group_age_seconds,
        oldest_group_age_seconds=oldest_group_age_seconds,
        oldest_prunable_group_age_seconds=oldest_prunable_group_age_seconds,
        groups=tuple(groups),
    )


def _build_sync_applied_retention_groups(
    loaded: LoadedConfig,
    *,
    issue_root: Path,
    entries: list[dict[str, Any]],
    keep_groups_per_issue: int,
) -> list[SyncAppliedRetentionGroup]:
    now = datetime.now(timezone.utc)
    grouped: dict[str, list[tuple[dict[str, Any], Path]]] = {}
    for index, entry in enumerate(entries):
        archive_path = _resolve_applied_manifest_archive_path(loaded, entry)
        if archive_path is None or not archive_path.exists():
            continue
        group_key = _manifest_group_key(entry, index=index)
        grouped.setdefault(group_key, []).append((entry, archive_path))

    ordered_groups = sorted(
        grouped.items(),
        key=lambda item: _retention_group_order_key(item[1]),
        reverse=True,
    )
    keep_group_keys = {group_key for group_key, _items in ordered_groups[:keep_groups_per_issue]}
    groups: list[SyncAppliedRetentionGroup] = []
    for group_key, items in ordered_groups:
        ordered_items = sorted(items, key=lambda item: _manifest_entry_sort_key(item[0]))
        timestamps = [_manifest_entry_timestamp(entry, archive_path) for entry, archive_path in ordered_items]
        archive_paths = [archive_path.resolve() for _entry, archive_path in ordered_items]
        actions = [
            str(entry.get("action"))
            for entry, _archive_path in ordered_items
            if entry.get("action") is not None
        ]
        groups.append(
            SyncAppliedRetentionGroup(
                group_key=group_key,
                tracker=issue_root.parent.name,
                issue_id=_parse_issue_root_id(issue_root.name),
                status="kept" if group_key in keep_group_keys else "prunable",
                actions=tuple(actions),
                archive_paths=tuple(
                    path.relative_to(loaded.sync_applied_dir.resolve()).as_posix() for path in archive_paths
                ),
                total_bytes=sum(path.stat().st_size for path in archive_paths),
                archive_file_count=len(archive_paths),
                newest_at=timestamps[-1].isoformat() if timestamps else None,
                oldest_at=timestamps[0].isoformat() if timestamps else None,
                newest_age_seconds=_age_seconds(now, timestamps[-1]) if timestamps else None,
                oldest_age_seconds=_age_seconds(now, timestamps[0]) if timestamps else None,
            )
        )
    return groups


def _retention_group_order_key(items: list[tuple[dict[str, Any], Path]]) -> tuple[str, str]:
    newest_timestamp = max(
        _manifest_entry_timestamp(entry, archive_path) for entry, archive_path in items
    )
    return (newest_timestamp.isoformat(), str(items[0][1]))


def _manifest_entry_timestamp(entry: dict[str, Any], archive_path: Path) -> datetime:
    applied_at = _coerce_text(entry.get("applied_at"))
    if applied_at:
        parsed = _parse_iso_datetime(applied_at)
        if parsed is not None:
            return parsed
    staged_at = _coerce_text(entry.get("staged_at"))
    if staged_at:
        parsed_staged_at = _parse_stamp_datetime(staged_at)
        if parsed_staged_at is not None:
            return parsed_staged_at
    return datetime.fromtimestamp(archive_path.stat().st_mtime, tz=timezone.utc)


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_stamp_datetime(value: str) -> datetime | None:
    for format_string in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S%fZ"):
        try:
            return datetime.strptime(value, format_string).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _age_seconds(now: datetime, timestamp: datetime) -> int:
    return max(0, int((now - timestamp).total_seconds()))


def _retention_issue_sort_key(summary: SyncAppliedRetentionIssueSummary) -> tuple[int, int, int, int, str]:
    priority = {
        "repair-needed": 0,
        "prunable": 1,
        "stable": 2,
    }.get(summary.status, 3)
    age_rank = summary.oldest_prunable_group_age_seconds or summary.oldest_group_age_seconds or 0
    issue_rank = summary.issue_id if summary.issue_id is not None else -1
    return (
        priority,
        -(summary.prunable_bytes),
        -(age_rank),
        issue_rank,
        summary.tracker,
    )


def _inspect_repaired_issue_manifest(
    loaded: LoadedConfig,
    issue_root: Path,
    entries: list[dict[str, Any]],
) -> AppliedSyncManifestReport:
    manifest_path = issue_root / "manifest.json"
    archive_files = sorted(
        path.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix()
        for path in issue_root.iterdir()
        if path.is_file() and path.name != "manifest.json"
    )
    findings: list[AppliedSyncManifestFinding] = []
    referenced_archives: set[str] = set()
    for entry in entries:
        archive_path = _resolve_applied_manifest_archive_path(loaded, entry)
        archived_relative_path = _resolve_applied_manifest_relative_path(loaded, entry)
        if archive_path is None or archived_relative_path is None or not archive_path.exists():
            findings.append(
                AppliedSyncManifestFinding(
                    code="dangling_archive_reference",
                    message="Manifest entry points to an archived artifact that does not exist.",
                    entry_key=_coerce_text(entry.get("entry_key")),
                    path=archived_relative_path,
                )
            )
            continue
        referenced_archives.add(archived_relative_path)
    for orphan in sorted(set(archive_files) - referenced_archives):
        findings.append(
            AppliedSyncManifestFinding(
                code="orphan_archive_file",
                message="Archived artifact exists under sync-applied but is not referenced by manifest.json.",
                path=orphan,
            )
        )
    _append_group_integrity_findings(findings, entries)
    return AppliedSyncManifestReport(
        tracker=issue_root.parent.name,
        issue_id=_parse_issue_root_id(issue_root.name),
        issue_root=issue_root,
        manifest_path=manifest_path,
        manifest_exists=True,
        archive_files=tuple(archive_files),
        findings=tuple(findings),
        manifest_entry_count=len(entries),
        referenced_archive_count=len(referenced_archives),
    )


def _append_group_integrity_findings(
    findings: list[AppliedSyncManifestFinding],
    entries: list[dict[str, Any]],
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, entry in enumerate(entries):
        group_key = _manifest_group_key(entry, index=index)
        grouped.setdefault(group_key, []).append(entry)
    for group_key, group_entries in grouped.items():
        ordered_group = sorted(group_entries, key=lambda item: _manifest_entry_sort_key(item))
        expected_entry_keys = [str(entry["entry_key"]) for entry in ordered_group if entry.get("entry_key")]
        expected_source_paths = [
            str(entry["source_relative_path"])
            for entry in ordered_group
            if entry.get("source_relative_path")
        ]
        expected_actions = [str(entry["action"]) for entry in ordered_group if entry.get("action")]
        for expected_index, entry in enumerate(ordered_group):
            handoff = entry.get("handoff")
            if not isinstance(handoff, dict):
                findings.append(
                    AppliedSyncManifestFinding(
                        code="missing_handoff_metadata",
                        message="Manifest entry is missing handoff metadata.",
                        entry_key=_coerce_text(entry.get("entry_key")),
                        path=_coerce_text(entry.get("archived_relative_path")),
                    )
                )
                continue
            mismatch = (
                handoff.get("group_key") != group_key
                or handoff.get("group_size") != len(ordered_group)
                or handoff.get("group_index") != expected_index
                or handoff.get("group_actions") != expected_actions
                or handoff.get("related_entry_keys") != expected_entry_keys
                or handoff.get("related_source_paths") != expected_source_paths
            )
            if mismatch:
                findings.append(
                    AppliedSyncManifestFinding(
                        code="handoff_group_mismatch",
                        message="handoff linkage does not match the current manifest group membership.",
                        entry_key=_coerce_text(entry.get("entry_key")),
                        path=_coerce_text(entry.get("archived_relative_path")),
                    )
                )


def _repair_issue_manifest_entries(
    loaded: LoadedConfig,
    issue_root: Path,
    raw_entries: list[object],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    canonical_by_archive: dict[str, dict[str, Any]] = {}
    stats = {
        "dropped_entries": 0,
        "adopted_archives": 0,
        "normalized_entries": 0,
    }
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            stats["dropped_entries"] += 1
            continue
        canonical_entry, changed = _canonicalize_applied_manifest_entry(loaded, issue_root, raw_entry)
        if canonical_entry is None:
            stats["dropped_entries"] += 1
            continue
        archive_key = str(canonical_entry["archived_relative_path"])
        existing = canonical_by_archive.get(archive_key)
        if existing is None:
            canonical_by_archive[archive_key] = canonical_entry
            if changed:
                stats["normalized_entries"] += 1
            continue
        preferred = _pick_preferred_manifest_entry(existing, canonical_entry)
        if preferred is canonical_entry and changed:
            stats["normalized_entries"] += 1
        if preferred is canonical_entry and preferred is not existing:
            canonical_by_archive[archive_key] = canonical_entry
        stats["dropped_entries"] += 1

    issue_archive_files = sorted(
        path for path in issue_root.iterdir() if path.is_file() and path.name != "manifest.json"
    )
    for archive_path in issue_archive_files:
        archived_relative_path = archive_path.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix()
        if archived_relative_path in canonical_by_archive:
            continue
        canonical_by_archive[archived_relative_path] = _reconstruct_applied_manifest_entry(loaded, archive_path)
        stats["adopted_archives"] += 1

    repaired_entries = sorted(
        canonical_by_archive.values(),
        key=_manifest_entry_sort_key,
    )
    _ensure_unique_manifest_entry_keys(repaired_entries)
    _rebuild_handoff_linkage(repaired_entries)
    return repaired_entries, stats


def _canonicalize_applied_manifest_entry(
    loaded: LoadedConfig,
    issue_root: Path,
    entry: dict[str, Any],
) -> tuple[dict[str, Any] | None, bool]:
    archive_path = _resolve_applied_manifest_archive_path(loaded, entry)
    if archive_path is None or not archive_path.exists():
        return None, False
    artifact = _safe_parse_applied_sync_artifact(loaded, archive_path)
    if artifact is None:
        return None, False
    canonical = dict(entry)
    changed = False

    archived_relative_path = archive_path.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix()
    source_relative_path = _coerce_text(canonical.get("source_relative_path")) or archived_relative_path
    applied_at = _coerce_text(canonical.get("applied_at")) or datetime.fromtimestamp(
        archive_path.stat().st_mtime,
        tz=timezone.utc,
    ).isoformat()

    replacements: dict[str, Any] = {
        "tracker": issue_root.parent.name,
        "issue_id": _parse_issue_root_id(issue_root.name),
        "action": _coerce_text(canonical.get("action")) or artifact.action,
        "format": _coerce_text(canonical.get("format")) or artifact.format,
        "applied_at": applied_at,
        "staged_at": _coerce_text(canonical.get("staged_at")) or artifact.staged_at,
        "summary": _coerce_text(canonical.get("summary")) or artifact.summary,
        "source_relative_path": source_relative_path,
        "archived_relative_path": archived_relative_path,
        "archived_path": str(archive_path),
        "effect": _coerce_text(canonical.get("effect")) or "Recovered applied sync artifact during manifest repair.",
    }
    for key, value in replacements.items():
        if canonical.get(key) != value:
            canonical[key] = value
            changed = True

    normalized = canonical.get("normalized")
    if not isinstance(normalized, dict):
        normalized = {}
        changed = True
    merged_normalized = dict(artifact.normalized)
    merged_normalized.update(normalized)
    merged_normalized.setdefault("links", {})
    if not isinstance(merged_normalized["links"], dict):
        merged_normalized["links"] = {}
    merged_normalized["links"].setdefault("self", source_relative_path)
    if merged_normalized != canonical.get("normalized"):
        canonical["normalized"] = merged_normalized
        changed = True

    entry_key = _coerce_text(canonical.get("entry_key")) or f"{issue_root.parent.name}:{source_relative_path}"
    if canonical.get("entry_key") != entry_key:
        canonical["entry_key"] = entry_key
        changed = True

    canonical_handoff = _normalize_manifest_handoff(canonical)
    if canonical_handoff != canonical.get("handoff"):
        canonical["handoff"] = canonical_handoff
        changed = True

    return canonical, changed


def _reconstruct_applied_manifest_entry(loaded: LoadedConfig, archive_path: Path) -> dict[str, Any]:
    artifact = _safe_parse_applied_sync_artifact(loaded, archive_path)
    if artifact is None:
        tracker = archive_path.parent.parent.name
        issue_id = _parse_issue_root_id(archive_path.parent.name)
        staged_at, action = _parse_staged_name(archive_path)
        relative_path = archive_path.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix()
        issue_key = f"issue:{issue_id}" if issue_id is not None else None
        entry_key = f"{tracker}:{relative_path}"
        group_key = entry_key
        return {
            "entry_key": entry_key,
            "tracker": tracker,
            "issue_id": issue_id,
            "action": action,
            "format": _infer_format(archive_path),
            "applied_at": datetime.fromtimestamp(archive_path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "staged_at": staged_at,
            "summary": action,
            "normalized": {
                "schema_version": NORMALIZED_SYNC_SCHEMA_VERSION,
                "artifact_role": _artifact_role(action),
                "issue_key": issue_key,
                "bundle_key": group_key,
                "links": {"self": relative_path},
                "refs": {},
            },
            "source_relative_path": relative_path,
            "archived_relative_path": relative_path,
            "archived_path": str(archive_path.resolve()),
            "effect": "Recovered applied sync artifact during manifest repair.",
            "handoff": {
                "group_key": group_key,
                "group_size": 1,
                "group_index": 0,
                "group_actions": [action],
                "related_entry_keys": [entry_key],
                "related_source_paths": [relative_path],
            },
        }
    applied_at = datetime.fromtimestamp(archive_path.stat().st_mtime, tz=timezone.utc).isoformat()
    source_relative_path = artifact.relative_path
    entry_key = f"{artifact.tracker}:{source_relative_path}"
    group_key = _coerce_text(artifact.normalized.get("bundle_key")) or entry_key
    return {
        "entry_key": entry_key,
        "tracker": artifact.tracker,
        "issue_id": artifact.issue_id,
        "action": artifact.action,
        "format": artifact.format,
        "applied_at": applied_at,
        "staged_at": artifact.staged_at,
        "summary": artifact.summary,
        "normalized": artifact.normalized,
        "source_relative_path": source_relative_path,
        "archived_relative_path": source_relative_path,
        "archived_path": str(archive_path.resolve()),
        "effect": "Recovered applied sync artifact during manifest repair.",
        "handoff": {
            "group_key": group_key,
            "group_size": 1,
            "group_index": 0,
            "group_actions": [artifact.action],
            "related_entry_keys": [entry_key],
            "related_source_paths": [source_relative_path],
        },
    }


def _safe_parse_applied_sync_artifact(loaded: LoadedConfig, archive_path: Path) -> SyncArtifact | None:
    try:
        return parse_sync_artifact(loaded, archive_path, state="applied")
    except Exception:  # noqa: BLE001
        return None


def _normalize_manifest_handoff(entry: dict[str, Any]) -> dict[str, Any]:
    handoff = entry.get("handoff")
    if not isinstance(handoff, dict):
        handoff = {}
    entry_key = _coerce_text(entry.get("entry_key")) or "entry-unknown"
    source_relative_path = _coerce_text(entry.get("source_relative_path")) or _coerce_text(entry.get("archived_relative_path")) or entry_key
    group_key = _coerce_text(handoff.get("group_key")) or _coerce_text(entry.get("entry_key")) or source_relative_path
    group_actions = handoff.get("group_actions")
    if not isinstance(group_actions, list) or not group_actions:
        group_actions = [entry.get("action")]
    related_entry_keys = handoff.get("related_entry_keys")
    if not isinstance(related_entry_keys, list) or not related_entry_keys:
        related_entry_keys = [entry_key]
    related_source_paths = handoff.get("related_source_paths")
    if not isinstance(related_source_paths, list) or not related_source_paths:
        related_source_paths = [source_relative_path]
    return {
        "group_key": group_key,
        "group_size": int(handoff.get("group_size") or 1),
        "group_index": int(handoff.get("group_index") or 0),
        "group_actions": [str(action) for action in group_actions if action is not None],
        "related_entry_keys": [str(value) for value in related_entry_keys if value is not None],
        "related_source_paths": [str(value) for value in related_source_paths if value is not None],
    }


def _pick_preferred_manifest_entry(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return max([left, right], key=_manifest_entry_quality_key)


def _manifest_entry_quality_key(entry: dict[str, Any]) -> tuple[int, str]:
    quality = 0
    for key in ("summary", "effect", "entry_key", "source_relative_path", "archived_relative_path"):
        if _coerce_text(entry.get(key)):
            quality += 1
    normalized = entry.get("normalized")
    if isinstance(normalized, dict) and normalized:
        quality += 1
    handoff = entry.get("handoff")
    if isinstance(handoff, dict) and handoff:
        quality += 1
    return (quality, _coerce_text(entry.get("applied_at")) or "")


def _ensure_unique_manifest_entry_keys(entries: list[dict[str, Any]]) -> None:
    seen: dict[str, int] = {}
    for entry in entries:
        raw_key = _coerce_text(entry.get("entry_key")) or "entry-unknown"
        count = seen.get(raw_key, 0)
        if count == 0:
            seen[raw_key] = 1
            entry["entry_key"] = raw_key
            continue
        seen[raw_key] = count + 1
        entry["entry_key"] = f"{raw_key}#repair-{count + 1}"


def _rebuild_handoff_linkage(entries: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, entry in enumerate(entries):
        grouped.setdefault(_manifest_group_key(entry, index=index), []).append(entry)
    for group_entries in grouped.values():
        ordered_group = sorted(group_entries, key=_manifest_entry_sort_key)
        group_actions = [str(entry["action"]) for entry in ordered_group if entry.get("action")]
        entry_keys = [str(entry["entry_key"]) for entry in ordered_group if entry.get("entry_key")]
        source_paths = [
            str(entry["source_relative_path"])
            for entry in ordered_group
            if entry.get("source_relative_path")
        ]
        group_key = _manifest_group_key(ordered_group[0], index=0)
        for index, entry in enumerate(ordered_group):
            entry["handoff"] = {
                "group_key": group_key,
                "group_size": len(ordered_group),
                "group_index": index,
                "group_actions": group_actions,
                "related_entry_keys": entry_keys,
                "related_source_paths": source_paths,
            }


def _manifest_entry_sort_key(entry: dict[str, Any]) -> tuple[str, int, str]:
    handoff = entry.get("handoff")
    if isinstance(handoff, dict):
        group_index = int(handoff.get("group_index") or 0)
    else:
        group_index = 0
    return (
        _coerce_text(entry.get("applied_at")) or "",
        group_index,
        _coerce_text(entry.get("archived_relative_path")) or "",
    )


def _manifest_group_key(entry: dict[str, Any], *, index: int) -> str:
    handoff = entry.get("handoff")
    if isinstance(handoff, dict):
        group_key = _coerce_text(handoff.get("group_key"))
        if group_key:
            return group_key
    normalized = entry.get("normalized")
    if isinstance(normalized, dict):
        group_key = _coerce_text(normalized.get("bundle_key"))
        if group_key:
            return group_key
    return _coerce_text(entry.get("entry_key")) or f"entry-{index}"


def _resolve_applied_manifest_relative_path(
    loaded: LoadedConfig,
    entry: dict[str, Any],
) -> str | None:
    archive_path = _resolve_applied_manifest_archive_path(loaded, entry)
    if archive_path is None:
        return None
    return archive_path.resolve().relative_to(loaded.sync_applied_dir.resolve()).as_posix()


def _resolve_applied_manifest_archive_path(
    loaded: LoadedConfig,
    entry: dict[str, Any],
) -> Path | None:
    archived_relative_path = _coerce_text(entry.get("archived_relative_path"))
    if archived_relative_path:
        return (loaded.sync_applied_dir / archived_relative_path).resolve()
    archived_path = _coerce_text(entry.get("archived_path"))
    if not archived_path:
        return None
    candidate = Path(archived_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (loaded.sync_applied_dir / candidate).resolve()


def _load_manifest_payload(manifest_path: Path) -> tuple[list[object], str | None]:
    if not manifest_path.exists():
        return [], None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], "invalid_json"
    if not isinstance(payload, list):
        return [], "invalid_format"
    return payload, None


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
