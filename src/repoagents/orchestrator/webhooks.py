from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from repoagents.utils.files import load_json_file


@dataclass(frozen=True, slots=True)
class WebhookDecision:
    provider: str
    event: str
    action: str | None
    issue_id: int | None
    should_run: bool
    summary: str
    reason: str


def load_webhook_payload(path: Path) -> dict[str, Any]:
    payload = load_json_file(path, default={})
    if not isinstance(payload, dict):
        raise ValueError("Webhook payload must be a JSON object.")
    return payload


def parse_github_webhook(event: str, payload: Mapping[str, Any]) -> WebhookDecision:
    normalized_event = event.strip().lower()
    raw_action = payload.get("action")
    action = str(raw_action).strip().lower() if raw_action is not None else None

    if normalized_event == "issues":
        return _parse_github_issue_event(normalized_event, action, payload)
    if normalized_event == "issue_comment":
        return _parse_github_issue_comment_event(normalized_event, action, payload)
    return _ignored(
        event=normalized_event,
        action=action,
        reason=f"unsupported GitHub webhook event '{normalized_event}'",
    )


def _parse_github_issue_event(
    event: str,
    action: str | None,
    payload: Mapping[str, Any],
) -> WebhookDecision:
    supported_actions = {"opened", "edited", "reopened", "labeled"}
    if action not in supported_actions:
        return _ignored(
            event=event,
            action=action,
            reason=f"unsupported issues action '{action or 'unknown'}'",
        )

    issue_id = _extract_issue_number(payload)
    if issue_id is None:
        return _ignored(event=event, action=action, reason="payload is missing issue.number")
    if _issue_state(payload) == "closed":
        return _ignored(event=event, action=action, issue_id=issue_id, reason="issue is closed")

    reason = f"GitHub issues.{action} event matched issue #{issue_id}."
    if action == "labeled":
        label_name = ((payload.get("label") or {}).get("name") or "").strip()
        if label_name:
            reason = f"GitHub issues.labeled event matched issue #{issue_id} (label={label_name})."
    return WebhookDecision(
        provider="github",
        event=event,
        action=action,
        issue_id=issue_id,
        should_run=True,
        summary=f"Trigger issue #{issue_id} from GitHub {event}.{action}.",
        reason=reason,
    )


def _parse_github_issue_comment_event(
    event: str,
    action: str | None,
    payload: Mapping[str, Any],
) -> WebhookDecision:
    if action != "created":
        return _ignored(
            event=event,
            action=action,
            reason=f"unsupported issue_comment action '{action or 'unknown'}'",
        )

    issue_id = _extract_issue_number(payload)
    if issue_id is None:
        return _ignored(event=event, action=action, reason="payload is missing issue.number")
    if _issue_state(payload) == "closed":
        return _ignored(event=event, action=action, issue_id=issue_id, reason="issue is closed")

    comment_payload = payload.get("comment") or {}
    author = ((comment_payload.get("user") or {}).get("login") or "unknown").strip()
    return WebhookDecision(
        provider="github",
        event=event,
        action=action,
        issue_id=issue_id,
        should_run=True,
        summary=f"Trigger issue #{issue_id} from GitHub {event}.{action}.",
        reason=f"GitHub issue_comment.created event matched issue #{issue_id} (comment_author={author}).",
    )


def _extract_issue_number(payload: Mapping[str, Any]) -> int | None:
    issue = payload.get("issue")
    if not isinstance(issue, Mapping):
        return None
    for key in ("number", "id"):
        value = issue.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _issue_state(payload: Mapping[str, Any]) -> str | None:
    issue = payload.get("issue")
    if not isinstance(issue, Mapping):
        return None
    state = issue.get("state")
    if state is None:
        return None
    return str(state).strip().lower()


def _ignored(
    *,
    event: str,
    action: str | None,
    reason: str,
    issue_id: int | None = None,
) -> WebhookDecision:
    return WebhookDecision(
        provider="github",
        event=event,
        action=action,
        issue_id=issue_id,
        should_run=False,
        summary="Ignore GitHub webhook payload.",
        reason=reason,
    )
