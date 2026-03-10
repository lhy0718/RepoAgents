from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import BaseModel, Field

from repoagents.models import DiffReport, IssueType, PublicationMode


class PolicyEvaluation(BaseModel):
    blocked: bool = False
    requires_human_review: bool = True
    auto_merge_candidate: bool = False
    publication_mode: PublicationMode = PublicationMode.HUMAN_APPROVAL
    findings: list[str] = Field(default_factory=list)
    summary: str = ""


class PolicyRules(BaseModel):
    blocked_secret_names: list[str] = Field(
        default_factory=lambda: [
            ".env",
            ".env.production",
            "id_rsa",
            "id_ed25519",
            "credentials.json",
        ]
    )
    blocked_secret_suffixes: list[str] = Field(
        default_factory=lambda: [
            ".pem",
            ".key",
            ".p12",
            ".pfx",
            ".kubeconfig",
        ]
    )
    sensitive_path_prefixes: list[str] = Field(
        default_factory=lambda: [
            ".github/workflows",
            ".github/actions",
            "deploy/",
            "deployment/",
            "infra/",
            "k8s/",
            "terraform/",
            "helm/",
            "ansible/",
            "ops/",
            "security/",
        ]
    )
    sensitive_path_segments: list[str] = Field(
        default_factory=lambda: [
            "auth",
            "security",
            "permissions",
            "rbac",
            "iam",
            "secrets",
            "credentials",
        ]
    )
    sensitive_name_tokens: list[str] = Field(
        default_factory=lambda: [
            "auth",
            "oauth",
            "permission",
            "rbac",
            "iam",
            "secret",
            "credential",
            "token",
            "vault",
        ]
    )
    large_deletion_threshold: int = 200
    ignored_large_deletion_prefixes: list[str] = Field(
        default_factory=lambda: [
            "vendor/",
            "dist/",
            "build/",
            "coverage/",
            "node_modules/",
            ".next/",
            "docs/_build/",
            "generated/",
            "gen/",
        ]
    )


def evaluate_policy(
    issue_type: IssueType,
    diff_report: DiffReport,
    allowed_auto_merge_types: list[str],
    requested_publication_mode: PublicationMode = PublicationMode.HUMAN_APPROVAL,
    rules: PolicyRules | None = None,
) -> PolicyEvaluation:
    active_rules = rules or PolicyRules()
    findings: list[str] = []
    touched_files = diff_report.changed_files + diff_report.added_files + diff_report.removed_files

    for rel_path in touched_files:
        path = PurePosixPath(rel_path)
        name = path.name.lower()
        if _is_secret_like(name, active_rules):
            findings.append(f"Sensitive secret-like file change blocked: {rel_path}")
        if _is_sensitive_path(rel_path, path, name, active_rules):
            findings.append(f"Sensitive infra/auth/deploy path requires human review: {rel_path}")

    if _should_flag_large_deletion(diff_report, active_rules):
        findings.append(
            f"Large deletion detected ({diff_report.total_removed_lines} removed lines); block automation."
        )

    docs_only = bool(touched_files) and all(
        path.endswith((".md", ".rst", ".txt")) for path in touched_files
    )
    tests_only = bool(touched_files) and all(
        path.startswith("tests/") or "/tests/" in path for path in touched_files
    )
    auto_merge_candidate = (
        issue_type.value in allowed_auto_merge_types
        or ("docs" in allowed_auto_merge_types and docs_only)
        or ("tests" in allowed_auto_merge_types and tests_only)
    )
    publication_mode = _select_publication_mode(
        auto_merge_candidate=auto_merge_candidate,
        requested_mode=requested_publication_mode,
        findings=findings,
    )
    summary = _build_policy_summary(
        auto_merge_candidate=auto_merge_candidate,
        publication_mode=publication_mode,
        findings=findings,
    )

    return PolicyEvaluation(
        blocked=bool(findings),
        requires_human_review=True,
        auto_merge_candidate=auto_merge_candidate and not findings,
        publication_mode=publication_mode,
        findings=findings,
        summary=summary,
    )


def _is_secret_like(name: str, rules: PolicyRules) -> bool:
    return name in rules.blocked_secret_names or any(
        name.endswith(suffix) for suffix in rules.blocked_secret_suffixes
    )


def _is_sensitive_path(
    rel_path: str,
    path: PurePosixPath,
    name: str,
    rules: PolicyRules,
) -> bool:
    normalized_path = rel_path.lower()
    if any(normalized_path.startswith(prefix) for prefix in rules.sensitive_path_prefixes):
        return True
    if any(segment.lower() in rules.sensitive_path_segments for segment in path.parts):
        return True
    return any(token in name for token in rules.sensitive_name_tokens)


def _should_flag_large_deletion(diff_report: DiffReport, rules: PolicyRules) -> bool:
    if diff_report.total_removed_lines < rules.large_deletion_threshold:
        return False
    touched_non_ignored = [
        rel_path
        for rel_path in diff_report.changed_files + diff_report.removed_files
        if not _is_ignored_large_deletion_path(rel_path, rules)
    ]
    if not touched_non_ignored:
        return False
    if _looks_like_move(diff_report, rules):
        return False
    return True


def _is_ignored_large_deletion_path(rel_path: str, rules: PolicyRules) -> bool:
    normalized_path = rel_path.lower()
    return any(
        normalized_path.startswith(prefix)
        or f"/{prefix.rstrip('/')}/" in normalized_path
        for prefix in rules.ignored_large_deletion_prefixes
    )


def _looks_like_move(diff_report: DiffReport, rules: PolicyRules) -> bool:
    removed = [
        PurePosixPath(path).name.lower()
        for path in diff_report.removed_files
        if not _is_ignored_large_deletion_path(path, rules)
    ]
    added = [
        PurePosixPath(path).name.lower()
        for path in diff_report.added_files
        if not _is_ignored_large_deletion_path(path, rules)
    ]
    if not removed or not added or diff_report.changed_files:
        return False
    added_names = set(added)
    return all(name in added_names for name in removed)


def _select_publication_mode(
    *,
    auto_merge_candidate: bool,
    requested_mode: PublicationMode,
    findings: list[str],
) -> PublicationMode:
    if findings:
        return PublicationMode.COMMENT_ONLY
    if auto_merge_candidate:
        return requested_mode
    return PublicationMode.HUMAN_APPROVAL


def _build_policy_summary(
    *,
    auto_merge_candidate: bool,
    publication_mode: PublicationMode,
    findings: list[str],
) -> str:
    if findings:
        return "Policy violations detected; reviewer must request changes."
    if auto_merge_candidate and publication_mode == PublicationMode.COMMENT_ONLY:
        return "Low-risk docs/tests change is limited to comment-only publication."
    if auto_merge_candidate and publication_mode == PublicationMode.DRAFT_PR:
        return "Low-risk docs/tests change may open a draft PR when writes are enabled."
    return "Human approval remains required before publishing changes."
