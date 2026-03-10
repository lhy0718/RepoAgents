from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse

from repoagents.config import LoadedConfig
from repoagents.models import IssueRef
from repoagents.models.domain import utc_now
from repoagents.tracker import build_tracker
from repoagents.tracker.github import GitHubTracker
from repoagents.utils.git import GitCommandError, is_git_repository, run_git
from repoagents.utils.files import write_text_file


VALID_GITHUB_SMOKE_FORMATS = ("json", "markdown")


class GitHubSmokeBuildResult:
    def __init__(self, output_paths: dict[str, Path], snapshot: dict[str, Any]) -> None:
        self.output_paths = output_paths
        self.snapshot = snapshot


def normalize_github_smoke_formats(
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
            for item in VALID_GITHUB_SMOKE_FORMATS:
                if item not in normalized:
                    normalized.append(item)
            continue
        if lowered not in VALID_GITHUB_SMOKE_FORMATS:
            raise ValueError(
                "Unsupported GitHub smoke format. Expected one of: json, markdown, all"
            )
        if lowered not in normalized:
            normalized.append(lowered)
    return tuple(normalized or ("json",))


def build_github_smoke_exports(
    *,
    snapshot: dict[str, Any],
    output_path: Path,
    formats: tuple[str, ...],
) -> GitHubSmokeBuildResult:
    export_paths = resolve_github_smoke_export_paths(output_path, formats)
    if "json" in export_paths:
        write_text_file(export_paths["json"], render_github_smoke_json(snapshot))
    if "markdown" in export_paths:
        write_text_file(export_paths["markdown"], render_github_smoke_markdown(snapshot))
    return GitHubSmokeBuildResult(output_paths=export_paths, snapshot=snapshot)


def resolve_github_smoke_export_paths(
    target: Path,
    formats: tuple[str, ...],
) -> dict[str, Path]:
    resolved = target.resolve()
    export_paths: dict[str, Path] = {}
    for export_format in formats:
        suffix = ".md" if export_format == "markdown" else ".json"
        export_paths[export_format] = resolved.with_suffix(suffix)
    return export_paths


def collect_github_auth_snapshot(loaded: LoadedConfig) -> dict[str, Any]:
    tracker = loaded.data.tracker
    token_env = tracker.token_env
    token_present = bool(os.getenv(token_env))
    gh_path = shutil.which("gh")
    gh_authenticated = False

    if tracker.mode.value == "fixture":
        return {
            "status": "not_applicable",
            "message": "fixture tracker mode does not require live GitHub authentication",
            "hint": None,
            "source": "fixture",
            "token_env": token_env,
            "token_present": token_present,
            "gh_path": gh_path,
            "gh_authenticated": False,
            "requires_token": False,
        }

    if token_present:
        return {
            "status": "ok",
            "message": f"{token_env} is set",
            "hint": None,
            "source": "token_env",
            "token_env": token_env,
            "token_present": True,
            "gh_path": gh_path,
            "gh_authenticated": False,
            "requires_token": True,
        }

    if gh_path:
        completed = subprocess.run(
            ["gh", "auth", "status", "--hostname", "github.com"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        gh_authenticated = completed.returncode == 0
        if gh_authenticated:
            return {
                "status": "warn",
                "message": (
                    f"gh auth is available via {gh_path}, but tracker.mode=rest still "
                    f"requires {token_env}"
                ),
                "hint": f"Export {token_env} before running live GitHub tracker operations.",
                "source": "gh_cli_only",
                "token_env": token_env,
                "token_present": False,
                "gh_path": gh_path,
                "gh_authenticated": True,
                "requires_token": True,
            }
        return {
            "status": "warn",
            "message": "gh is installed but not authenticated",
            "hint": f"Run `gh auth login` and export {token_env} for REST tracker access.",
            "source": "missing",
            "token_env": token_env,
            "token_present": False,
            "gh_path": gh_path,
            "gh_authenticated": False,
            "requires_token": True,
        }

    return {
        "status": "warn",
        "message": f"{token_env} is not set",
        "hint": f"Set {token_env} for live GitHub REST access.",
        "source": "missing",
        "token_env": token_env,
        "token_present": False,
        "gh_path": None,
        "gh_authenticated": False,
        "requires_token": True,
    }


def _load_github_smoke_fixture_snapshot(
    loaded: LoadedConfig,
    *,
    rendered_at: str,
    issue_id: int | None,
    issue_limit: int,
) -> dict[str, Any] | None:
    raw_path = loaded.data.tracker.smoke_fixture_path
    if not raw_path:
        return None
    fixture_path = loaded.resolve(raw_path)
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"GitHub smoke fixture not found at {fixture_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"GitHub smoke fixture at {fixture_path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"GitHub smoke fixture at {fixture_path} must contain a JSON object"
        )

    auth = _mapping(payload.get("auth"))
    repo_access = _mapping(payload.get("repo_access"))
    branch_policy = _mapping(payload.get("branch_policy"))
    origin = _mapping(payload.get("origin"))
    publish = _mapping(payload.get("publish"))
    issues = _mapping(payload.get("issues"))
    sampled_issue = _mapping(payload.get("sampled_issue"))
    summary = _mapping(payload.get("summary"))
    meta = _mapping(payload.get("meta"))

    return {
        "meta": {
            **meta,
            "kind": "github_smoke",
            "rendered_at": rendered_at,
            "repo_root": str(loaded.repo_root),
            "tracker_repo": loaded.data.tracker.repo,
            "issue_limit": max(1, issue_limit),
            "requested_issue_id": issue_id,
            "fixture_path": str(fixture_path),
            "source": "fixture",
        },
        "summary": {
            "status": summary.get("status", "attention"),
            "message": (
                summary.get("message")
                or publish.get("message")
                or repo_access.get("message")
                or "loaded GitHub smoke snapshot from fixture"
            ),
            "open_issue_count": int(summary.get("open_issue_count", issues.get("count", 0)) or 0),
            "sampled_issue_id": (
                summary.get("sampled_issue_id")
                if summary.get("sampled_issue_id") is not None
                else sampled_issue.get("issue_id")
            ),
            "write_comments_enabled": bool(
                summary.get("write_comments_enabled", publish.get("write_comments_enabled", False))
            ),
            "open_pr_enabled": bool(
                summary.get("open_pr_enabled", publish.get("open_pr_enabled", False))
            ),
            "auth_status": summary.get("auth_status", auth.get("status", "unknown")),
            "repo_access_status": summary.get("repo_access_status", repo_access.get("status", "unknown")),
            "branch_policy_status": summary.get(
                "branch_policy_status", branch_policy.get("status", "unknown")
            ),
            "publish_status": summary.get("publish_status", publish.get("status", "unknown")),
        },
        "auth": auth,
        "repo_access": repo_access,
        "branch_policy": branch_policy,
        "origin": origin,
        "publish": publish,
        "issues": issues,
        "sampled_issue": sampled_issue or None,
    }


def collect_github_origin_snapshot(loaded: LoadedConfig) -> dict[str, Any]:
    tracker = loaded.data.tracker
    if tracker.mode.value == "fixture":
        return {
            "status": "not_applicable",
            "message": "fixture tracker mode does not use git origin preflight",
            "hint": None,
            "remote_url": None,
            "repo_slug": None,
            "matches_tracker_repo": None,
        }
    if not is_git_repository(loaded.repo_root):
        return {
            "status": "issues",
            "message": f"{loaded.repo_root} is not a git repository",
            "hint": "Initialize a git repository before enabling PR publish paths.",
            "remote_url": None,
            "repo_slug": None,
            "matches_tracker_repo": None,
        }
    try:
        remote_url = run_git(["remote", "get-url", "origin"], loaded.repo_root)
    except GitCommandError:
        return {
            "status": "issues",
            "message": "git remote origin is not configured",
            "hint": "Add an origin remote that points at tracker.repo before enabling PR publish.",
            "remote_url": None,
            "repo_slug": None,
            "matches_tracker_repo": None,
        }

    repo_slug = extract_git_remote_repo_slug(remote_url)
    if repo_slug is None:
        return {
            "status": "warn",
            "message": f"could not derive owner/name from origin remote ({remote_url})",
            "hint": "Use a standard git remote URL so RepoAgents can verify it matches tracker.repo.",
            "remote_url": remote_url,
            "repo_slug": None,
            "matches_tracker_repo": None,
        }
    if repo_slug != tracker.repo:
        return {
            "status": "issues",
            "message": f"origin remote points at {repo_slug}, expected {tracker.repo}",
            "hint": "Point git origin at the same repo slug configured in tracker.repo.",
            "remote_url": remote_url,
            "repo_slug": repo_slug,
            "matches_tracker_repo": False,
        }
    return {
        "status": "ok",
        "message": f"origin remote matches tracker.repo ({repo_slug})",
        "hint": None,
        "remote_url": remote_url,
        "repo_slug": repo_slug,
        "matches_tracker_repo": True,
    }


async def collect_github_live_repo_snapshots(
    loaded: LoadedConfig,
    *,
    tracker: GitHubTracker | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture_snapshot = _load_github_smoke_fixture_snapshot(
        loaded,
        rendered_at=utc_now().isoformat(),
        issue_id=None,
        issue_limit=5,
    )
    if fixture_snapshot is not None:
        return (
            _mapping(fixture_snapshot.get("repo_access")),
            _mapping(fixture_snapshot.get("branch_policy")),
        )
    managed_tracker = tracker
    should_close = False
    if managed_tracker is None:
        managed_tracker = _build_github_tracker(loaded)
        should_close = True
    try:
        repo_access = await collect_github_repo_access_snapshot(loaded, tracker=managed_tracker)
        branch_policy = await collect_github_branch_policy_snapshot(
            loaded,
            tracker=managed_tracker,
            repo_access_snapshot=repo_access,
        )
        return repo_access, branch_policy
    finally:
        if should_close and managed_tracker is not None:
            await managed_tracker.aclose()


async def collect_github_repo_access_snapshot(
    loaded: LoadedConfig,
    *,
    tracker: GitHubTracker | None = None,
) -> dict[str, Any]:
    if loaded.data.tracker.mode.value == "fixture":
        return {
            "status": "not_applicable",
            "message": "fixture tracker mode does not probe live repo metadata",
            "full_name": loaded.data.tracker.repo,
            "default_branch": None,
            "private": None,
            "permissions": {},
        }

    managed_tracker = tracker
    should_close = False
    if managed_tracker is None:
        managed_tracker = _build_github_tracker(loaded)
        should_close = True
    try:
        repo_info = await managed_tracker.get_repo_info()
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "issues",
            "message": f"could not load repo metadata: {exc}",
            "full_name": loaded.data.tracker.repo,
            "default_branch": None,
            "private": None,
            "permissions": {},
        }
    finally:
        if should_close and managed_tracker is not None:
            await managed_tracker.aclose()

    return {
        "status": "ok",
        "message": (
            f"loaded repo metadata for {repo_info.get('full_name') or loaded.data.tracker.repo}"
        ),
        "full_name": repo_info.get("full_name") or loaded.data.tracker.repo,
        "default_branch": repo_info.get("default_branch"),
        "private": repo_info.get("private"),
        "permissions": _mapping(repo_info.get("permissions")),
    }


async def collect_github_branch_policy_snapshot(
    loaded: LoadedConfig,
    *,
    tracker: GitHubTracker | None = None,
    repo_access_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if loaded.data.tracker.mode.value == "fixture":
        return {
            "status": "not_applicable",
            "message": "fixture tracker mode does not inspect default-branch policy",
            "hint": None,
            "default_branch": None,
            "local_branch": None,
            "local_matches_default_branch": None,
            "protected": None,
            "protection_details_status": "not_applicable",
            "required_pull_request_reviews": None,
            "required_approving_review_count": None,
            "required_status_checks": None,
            "required_status_check_context_count": 0,
            "enforce_admins": None,
            "warnings": (),
            "notes": (),
        }

    managed_tracker = tracker
    should_close = False
    if managed_tracker is None:
        managed_tracker = _build_github_tracker(loaded)
        should_close = True

    try:
        repo_access = repo_access_snapshot or await collect_github_repo_access_snapshot(
            loaded,
            tracker=managed_tracker,
        )
        if repo_access.get("status") != "ok":
            return {
                "status": "not_applicable",
                "message": "repo metadata probe failed before default-branch policy inspection",
                "hint": None,
                "default_branch": None,
                "local_branch": _read_local_git_branch(loaded.repo_root),
                "local_matches_default_branch": None,
                "protected": None,
                "protection_details_status": "not_applicable",
                "required_pull_request_reviews": None,
                "required_approving_review_count": None,
                "required_status_checks": None,
                "required_status_check_context_count": 0,
                "enforce_admins": None,
                "warnings": (),
                "notes": (),
            }

        default_branch = str(repo_access.get("default_branch") or "").strip()
        local_branch = _read_local_git_branch(loaded.repo_root)
        local_matches_default = (
            None
            if not local_branch or not default_branch
            else local_branch == default_branch
        )
        if not default_branch:
            return {
                "status": "warn",
                "message": "repo metadata did not report a default branch",
                "hint": "Verify the repository default branch before enabling unattended PR publish.",
                "default_branch": None,
                "local_branch": local_branch,
                "local_matches_default_branch": None,
                "protected": None,
                "protection_details_status": "not_applicable",
                "required_pull_request_reviews": None,
                "required_approving_review_count": None,
                "required_status_checks": None,
                "required_status_check_context_count": 0,
                "enforce_admins": None,
                "warnings": ("repo metadata did not report a default branch",),
                "notes": (),
            }

        try:
            branch_info = await managed_tracker.get_branch_info(default_branch)
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "warn",
                "message": f"could not inspect default branch {default_branch}: {exc}",
                "hint": "Verify tracker.repo and token permissions, then retry the branch policy probe.",
                "default_branch": default_branch,
                "local_branch": local_branch,
                "local_matches_default_branch": local_matches_default,
                "protected": None,
                "protection_details_status": "warn",
                "required_pull_request_reviews": None,
                "required_approving_review_count": None,
                "required_status_checks": None,
                "required_status_check_context_count": 0,
                "enforce_admins": None,
                "warnings": (f"could not inspect default branch {default_branch}",),
                "notes": _build_branch_policy_notes(local_branch, default_branch, local_matches_default),
            }

        protected = bool(branch_info.get("protected"))
        protection_details_status = "not_applicable"
        protection_payload: dict[str, Any] = {}
        warnings: list[str] = []
        notes = list(
            _build_branch_policy_notes(
                local_branch,
                default_branch,
                local_matches_default,
            )
        )

        if not protected:
            warnings.append(f"default branch {default_branch} is not protected")
        else:
            try:
                protection_payload = await managed_tracker.get_branch_protection(default_branch)
            except Exception:  # noqa: BLE001
                protection_details_status = "warn"
                warnings.append(
                    f"could not read detailed protection policy for default branch {default_branch}"
                )
            else:
                protection_details_status = "ok"

        review_policy = _mapping(protection_payload.get("required_pull_request_reviews"))
        required_status_checks_payload = _mapping(protection_payload.get("required_status_checks"))
        status_check_contexts = _collect_status_check_contexts(required_status_checks_payload)
        required_pull_request_reviews = bool(review_policy) if protection_details_status == "ok" else None
        required_approving_review_count = (
            review_policy.get("required_approving_review_count")
            if protection_details_status == "ok"
            else None
        )
        required_status_checks = (
            bool(status_check_contexts or required_status_checks_payload.get("checks"))
            if protection_details_status == "ok"
            else None
        )
        enforce_admins = (
            _mapping(protection_payload.get("enforce_admins")).get("enabled")
            if protection_details_status == "ok"
            else None
        )

        if protection_details_status == "ok":
            if not required_pull_request_reviews or required_approving_review_count in (None, 0):
                warnings.append(
                    f"default branch {default_branch} does not require pull request reviews"
                )
            if not required_status_checks:
                warnings.append(
                    f"default branch {default_branch} has no required status checks"
                )
            if enforce_admins is False:
                notes.append(
                    f"default branch {default_branch} does not enforce protections for admins"
                )

        message = (
            "; ".join(warnings)
            if warnings
            else (
                f"default branch {default_branch} is protected; "
                f"reviews_required={bool(required_pull_request_reviews)} "
                f"status_checks_required={bool(required_status_checks)}"
            )
        )
        hint = None
        if warnings:
            if any("not protected" in warning for warning in warnings):
                hint = (
                    "Protect the default branch or enable equivalent repository rulesets "
                    "before unattended live PR publish."
                )
            elif any("could not read detailed protection policy" in warning for warning in warnings):
                hint = (
                    "Use a token that can read branch protection or verify repository rulesets "
                    "manually before unattended live PR publish."
                )
            else:
                hint = (
                    "Require pull request reviews and status checks on the default branch "
                    "before unattended live PR publish."
                )

        return {
            "status": "warn" if warnings else "ok",
            "message": message,
            "hint": hint,
            "default_branch": default_branch,
            "local_branch": local_branch,
            "local_matches_default_branch": local_matches_default,
            "protected": protected,
            "protection_details_status": protection_details_status,
            "required_pull_request_reviews": required_pull_request_reviews,
            "required_approving_review_count": required_approving_review_count,
            "required_status_checks": required_status_checks,
            "required_status_check_context_count": len(status_check_contexts),
            "enforce_admins": enforce_admins,
            "warnings": tuple(warnings),
            "notes": tuple(notes),
        }
    finally:
        if should_close and managed_tracker is not None:
            await managed_tracker.aclose()


def collect_github_publish_readiness(
    loaded: LoadedConfig,
    *,
    auth_snapshot: dict[str, Any] | None = None,
    origin_snapshot: dict[str, Any] | None = None,
    repo_access_snapshot: dict[str, Any] | None = None,
    branch_policy_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tracker = loaded.data.tracker
    if tracker.mode.value == "fixture":
        return {
            "status": "not_applicable",
            "message": "fixture tracker mode does not execute live GitHub writes",
            "hint": None,
            "write_comments_enabled": False,
            "open_pr_enabled": False,
            "comment_writes_ready": False,
            "pr_writes_ready": False,
            "warnings": (),
        }

    auth = auth_snapshot or collect_github_auth_snapshot(loaded)
    origin = origin_snapshot or collect_github_origin_snapshot(loaded)
    repo_access = repo_access_snapshot or {}
    branch_policy = branch_policy_snapshot or {}
    write_comments_enabled = loaded.data.safety.allow_write_comments
    open_pr_enabled = loaded.data.safety.allow_open_pr

    if not write_comments_enabled and not open_pr_enabled:
        return {
            "status": "ok",
            "message": "live GitHub writes are disabled by safety policy",
            "hint": "Enable safety.allow_write_comments or safety.allow_open_pr when you are ready to publish.",
            "write_comments_enabled": False,
            "open_pr_enabled": False,
            "comment_writes_ready": False,
            "pr_writes_ready": False,
            "warnings": (),
        }

    warnings: list[str] = []
    comment_writes_ready = True
    pr_writes_ready = True
    token_ready = bool(auth.get("token_present"))

    if write_comments_enabled and not token_ready:
        comment_writes_ready = False
        warnings.append(f"comment writes require {tracker.token_env}")

    if open_pr_enabled:
        if not token_ready:
            pr_writes_ready = False
            warnings.append(f"PR publish requires {tracker.token_env}")
        origin_status = origin.get("status")
        if origin_status != "ok":
            pr_writes_ready = False
            warnings.append(str(origin.get("message") or "git origin preflight failed"))
        permissions = _mapping(repo_access.get("permissions"))
        if repo_access.get("status") == "ok" and permissions.get("push") is False:
            pr_writes_ready = False
            warnings.append("repo metadata reports push permission=false")
        if repo_access.get("status") == "ok" and not repo_access.get("default_branch"):
            pr_writes_ready = False
            warnings.append("repo metadata did not report a default branch")
        if branch_policy.get("status") == "warn":
            pr_writes_ready = False
            branch_warnings = branch_policy.get("warnings")
            if isinstance(branch_warnings, tuple):
                warnings.extend(
                    f"branch policy: {warning}"
                    for warning in branch_warnings
                    if isinstance(warning, str)
                )

    if warnings:
        return {
            "status": "warn",
            "message": "; ".join(warnings),
            "hint": "Resolve the warning set before enabling unattended live GitHub publish flows.",
            "write_comments_enabled": write_comments_enabled,
            "open_pr_enabled": open_pr_enabled,
            "comment_writes_ready": comment_writes_ready,
            "pr_writes_ready": pr_writes_ready,
            "warnings": tuple(warnings),
        }

    enabled_parts: list[str] = []
    if write_comments_enabled:
        enabled_parts.append("comment writes")
    if open_pr_enabled:
        enabled_parts.append("draft PR publish")
    enabled_label = " and ".join(enabled_parts) if enabled_parts else "live writes"
    return {
        "status": "ok",
        "message": f"{enabled_label} preflight checks passed",
        "hint": None,
        "write_comments_enabled": write_comments_enabled,
        "open_pr_enabled": open_pr_enabled,
        "comment_writes_ready": comment_writes_ready,
        "pr_writes_ready": pr_writes_ready,
        "warnings": (),
    }


async def build_github_smoke_snapshot(
    *,
    loaded: LoadedConfig,
    tracker: GitHubTracker,
    issue_id: int | None = None,
    issue_limit: int = 5,
) -> dict[str, Any]:
    rendered_at = utc_now().isoformat()
    fixture_snapshot = _load_github_smoke_fixture_snapshot(
        loaded,
        rendered_at=rendered_at,
        issue_id=issue_id,
        issue_limit=issue_limit,
    )
    if fixture_snapshot is not None:
        return fixture_snapshot
    auth = collect_github_auth_snapshot(loaded)
    origin = collect_github_origin_snapshot(loaded)
    repo_access: dict[str, Any]
    branch_policy: dict[str, Any]
    issues_section: dict[str, Any]
    sampled_issue: dict[str, Any] | None = None

    repo_access, branch_policy = await collect_github_live_repo_snapshots(
        loaded,
        tracker=tracker,
    )
    if repo_access.get("status") != "ok":
        issues_section = {
            "status": "not_applicable",
            "message": "repo metadata probe failed before issue sampling",
            "count": 0,
            "sampled": [],
        }
    else:
        try:
            issues = await tracker.list_open_issues()
        except Exception as exc:  # noqa: BLE001
            issues_section = {
                "status": "issues",
                "message": f"could not list open issues: {exc}",
                "count": 0,
                "sampled": [],
            }
        else:
            sample_count = max(1, issue_limit)
            sampled = [
                {
                    "id": issue.id,
                    "title": issue.title,
                    "labels": list(issue.labels),
                    "url": issue.url,
                }
                for issue in issues[:sample_count]
            ]
            issues_section = {
                "status": "ok",
                "message": f"loaded {len(issues)} open issue(s)",
                "count": len(issues),
                "sampled": sampled,
            }
            selected_issue_id = issue_id or (issues[0].id if issues else None)
            if selected_issue_id is not None:
                try:
                    issue = await tracker.get_issue(selected_issue_id)
                except Exception as exc:  # noqa: BLE001
                    sampled_issue = {
                        "status": "issues",
                        "message": f"could not load issue #{selected_issue_id}: {exc}",
                        "issue_id": selected_issue_id,
                    }
                else:
                    sampled_issue = _serialize_issue_snapshot(issue)

    publish = collect_github_publish_readiness(
        loaded,
        auth_snapshot=auth,
        origin_snapshot=origin,
        repo_access_snapshot=repo_access,
        branch_policy_snapshot=branch_policy,
    )

    overall_status = "clean"
    for status in (
        repo_access.get("status"),
        branch_policy.get("status"),
        issues_section.get("status"),
        auth.get("status"),
        publish.get("status"),
        sampled_issue.get("status") if isinstance(sampled_issue, dict) else "ok",
    ):
        if status == "issues":
            overall_status = "issues"
            break
        if status == "warn":
            overall_status = "attention"

    summary_message = (
        repo_access.get("message")
        if overall_status == "issues"
        else publish.get("message") or issues_section.get("message")
    )
    return {
        "meta": {
            "kind": "github_smoke",
            "rendered_at": rendered_at,
            "repo_root": str(loaded.repo_root),
            "tracker_repo": loaded.data.tracker.repo,
            "issue_limit": max(1, issue_limit),
            "requested_issue_id": issue_id,
        },
        "summary": {
            "status": overall_status,
            "message": summary_message,
            "open_issue_count": issues_section.get("count", 0),
            "sampled_issue_id": sampled_issue.get("issue_id") if isinstance(sampled_issue, dict) else None,
            "write_comments_enabled": publish.get("write_comments_enabled", False),
            "open_pr_enabled": publish.get("open_pr_enabled", False),
            "auth_status": auth.get("status", "unknown"),
            "repo_access_status": repo_access.get("status", "unknown"),
            "branch_policy_status": branch_policy.get("status", "unknown"),
            "publish_status": publish.get("status", "unknown"),
        },
        "auth": auth,
        "repo_access": repo_access,
        "branch_policy": branch_policy,
        "origin": origin,
        "publish": publish,
        "issues": issues_section,
        "sampled_issue": sampled_issue,
    }


def render_github_smoke_text(snapshot: dict[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    auth = _mapping(snapshot.get("auth"))
    repo_access = _mapping(snapshot.get("repo_access"))
    branch_policy = _mapping(snapshot.get("branch_policy"))
    origin = _mapping(snapshot.get("origin"))
    publish = _mapping(snapshot.get("publish"))
    issues = _mapping(snapshot.get("issues"))
    sampled_issue = _mapping(snapshot.get("sampled_issue"))

    lines = [
        "GitHub smoke: "
        f"status={summary.get('status', 'unknown')} "
        f"repo={snapshot.get('meta', {}).get('tracker_repo', 'n/a')} "
        f"open_issues={issues.get('count', 0)}",
        f"Summary: {summary.get('message', 'n/a')}",
        f"Auth: {auth.get('status', 'unknown')} ({auth.get('message', 'n/a')})",
        f"Repo access: {repo_access.get('status', 'unknown')} ({repo_access.get('message', 'n/a')})",
        f"Branch policy: {branch_policy.get('status', 'unknown')} ({branch_policy.get('message', 'n/a')})",
        f"Origin: {origin.get('status', 'unknown')} ({origin.get('message', 'n/a')})",
        f"Publish readiness: {publish.get('status', 'unknown')} ({publish.get('message', 'n/a')})",
    ]
    if sampled_issue:
        lines.append(
            "Sampled issue: "
            f"#{sampled_issue.get('issue_id', 'n/a')} "
            f"{sampled_issue.get('title', 'n/a')} "
            f"comments={sampled_issue.get('comment_count', 0)}"
        )
    else:
        lines.append("Sampled issue: none")
    return "\n".join(lines) + "\n"


def render_github_smoke_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True)


def render_github_smoke_markdown(snapshot: dict[str, Any]) -> str:
    meta = _mapping(snapshot.get("meta"))
    summary = _mapping(snapshot.get("summary"))
    auth = _mapping(snapshot.get("auth"))
    repo_access = _mapping(snapshot.get("repo_access"))
    branch_policy = _mapping(snapshot.get("branch_policy"))
    origin = _mapping(snapshot.get("origin"))
    publish = _mapping(snapshot.get("publish"))
    issues = _mapping(snapshot.get("issues"))
    sampled_issue = _mapping(snapshot.get("sampled_issue"))

    lines = [
        "# GitHub smoke report",
        "",
        f"- rendered_at: {meta.get('rendered_at', '-')}",
        f"- repo_root: {meta.get('repo_root', '-')}",
        f"- tracker_repo: {meta.get('tracker_repo', '-')}",
        f"- requested_issue_id: {meta.get('requested_issue_id', '-')}",
        "",
        "## Summary",
        f"- status: {summary.get('status', '-')}",
        f"- message: {summary.get('message', '-')}",
        f"- open_issue_count: {summary.get('open_issue_count', 0)}",
        f"- write_comments_enabled: {summary.get('write_comments_enabled', False)}",
        f"- open_pr_enabled: {summary.get('open_pr_enabled', False)}",
        "",
        "## Auth",
        f"- status: {auth.get('status', '-')}",
        f"- message: {auth.get('message', '-')}",
        f"- token_env: {auth.get('token_env', '-')}",
        f"- source: {auth.get('source', '-')}",
        "",
        "## Repo access",
        f"- status: {repo_access.get('status', '-')}",
        f"- message: {repo_access.get('message', '-')}",
        f"- full_name: {repo_access.get('full_name', '-')}",
        f"- default_branch: {repo_access.get('default_branch', '-')}",
        f"- private: {repo_access.get('private', '-')}",
        "",
        "## Branch policy",
        f"- status: {branch_policy.get('status', '-')}",
        f"- message: {branch_policy.get('message', '-')}",
        f"- default_branch: {branch_policy.get('default_branch', '-')}",
        f"- local_branch: {branch_policy.get('local_branch', '-')}",
        f"- protected: {branch_policy.get('protected', '-')}",
        f"- required_pull_request_reviews: {branch_policy.get('required_pull_request_reviews', '-')}",
        f"- required_status_checks: {branch_policy.get('required_status_checks', '-')}",
        f"- required_status_check_context_count: {branch_policy.get('required_status_check_context_count', 0)}",
        "",
        "## Origin",
        f"- status: {origin.get('status', '-')}",
        f"- message: {origin.get('message', '-')}",
        f"- remote_url: {origin.get('remote_url', '-')}",
        f"- repo_slug: {origin.get('repo_slug', '-')}",
        "",
        "## Publish readiness",
        f"- status: {publish.get('status', '-')}",
        f"- message: {publish.get('message', '-')}",
        f"- comment_writes_ready: {publish.get('comment_writes_ready', False)}",
        f"- pr_writes_ready: {publish.get('pr_writes_ready', False)}",
        "",
        "## Issues",
        f"- status: {issues.get('status', '-')}",
        f"- message: {issues.get('message', '-')}",
        f"- count: {issues.get('count', 0)}",
    ]
    sampled = issues.get("sampled")
    if isinstance(sampled, list) and sampled:
        lines.append("- sampled:")
        for entry in sampled:
            if not isinstance(entry, dict):
                continue
            lines.append(f"  - #{entry.get('id', '-')} {entry.get('title', '-')}")
    branch_warnings = branch_policy.get("warnings")
    if isinstance(branch_warnings, tuple) and branch_warnings:
        lines.extend(["", "## Branch policy warnings"])
        for warning in branch_warnings:
            if isinstance(warning, str):
                lines.append(f"- {warning}")
    branch_notes = branch_policy.get("notes")
    if isinstance(branch_notes, tuple) and branch_notes:
        lines.extend(["", "## Branch policy notes"])
        for note in branch_notes:
            if isinstance(note, str):
                lines.append(f"- {note}")
    lines.extend(["", "## Sampled issue"])
    if not sampled_issue:
        lines.append("- none")
    else:
        lines.extend(
            [
                f"- status: {sampled_issue.get('status', '-')}",
                f"- message: {sampled_issue.get('message', '-')}",
                f"- issue_id: {sampled_issue.get('issue_id', '-')}",
                f"- title: {sampled_issue.get('title', '-')}",
                f"- comment_count: {sampled_issue.get('comment_count', 0)}",
                f"- labels: {', '.join(sampled_issue.get('labels', [])) or '-'}",
            ]
        )
    return "\n".join(lines) + "\n"


def extract_git_remote_repo_slug(remote_url: str) -> str | None:
    value = remote_url.strip()
    if not value:
        return None

    path: str | None = None
    if "://" not in value and ":" in value:
        prefix, suffix = value.split(":", 1)
        if "@" in prefix or "." in prefix:
            path = suffix
    if path is None:
        parsed = urlparse(value)
        path = parsed.path or None
    if path is None:
        return None
    normalized = path.strip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    parts = [part for part in normalized.split("/") if part]
    if len(parts) < 2:
        return None
    return "/".join(parts[-2:])


def _serialize_issue_snapshot(issue: IssueRef) -> dict[str, Any]:
    return {
        "status": "ok",
        "message": f"loaded issue #{issue.id}",
        "issue_id": issue.id,
        "title": issue.title,
        "labels": list(issue.labels),
        "comment_count": len(issue.comments),
        "url": issue.url,
    }


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _build_github_tracker(loaded: LoadedConfig) -> GitHubTracker:
    tracker = build_tracker(loaded, dry_run=False)
    if not isinstance(tracker, GitHubTracker):
        raise TypeError("GitHub health checks require a GitHub tracker instance")
    return tracker


def _read_local_git_branch(repo_root: Path) -> str | None:
    if not is_git_repository(repo_root):
        return None
    try:
        branch = run_git(["branch", "--show-current"], repo_root)
    except GitCommandError:
        return None
    return branch or None


def _build_branch_policy_notes(
    local_branch: str | None,
    default_branch: str,
    local_matches_default: bool | None,
) -> tuple[str, ...]:
    notes: list[str] = []
    if local_branch and local_matches_default is False:
        notes.append(
            f"local HEAD is {local_branch}; staged publish will still target default branch {default_branch}"
        )
    return tuple(notes)


def _collect_status_check_contexts(required_status_checks_payload: dict[str, Any]) -> tuple[str, ...]:
    contexts = required_status_checks_payload.get("contexts")
    if isinstance(contexts, list):
        return tuple(str(item) for item in contexts if str(item).strip())
    checks = required_status_checks_payload.get("checks")
    if isinstance(checks, list):
        names: list[str] = []
        for item in checks:
            if isinstance(item, dict):
                name = str(item.get("context") or item.get("name") or "").strip()
                if name:
                    names.append(name)
        return tuple(names)
    return ()
