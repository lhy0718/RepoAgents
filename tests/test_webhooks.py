from __future__ import annotations

import json
from pathlib import Path

import pytest

from repoagents.orchestrator import load_webhook_payload, parse_github_webhook


def test_parse_github_issues_webhook_accepts_supported_issue_actions() -> None:
    decision = parse_github_webhook(
        "issues",
        {
            "action": "labeled",
            "label": {"name": "needs-triage"},
            "issue": {"number": 42, "state": "open"},
        },
    )

    assert decision.should_run is True
    assert decision.issue_id == 42
    assert decision.action == "labeled"
    assert "label=needs-triage" in decision.reason


def test_parse_github_issue_comment_webhook_rejects_closed_issues() -> None:
    decision = parse_github_webhook(
        "issue_comment",
        {
            "action": "created",
            "issue": {"number": 7, "state": "closed"},
            "comment": {"user": {"login": "octocat"}},
        },
    )

    assert decision.should_run is False
    assert decision.issue_id == 7
    assert decision.reason == "issue is closed"


def test_load_webhook_payload_requires_json_object(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ValueError, match="Webhook payload must be a JSON object."):
        load_webhook_payload(payload_path)
