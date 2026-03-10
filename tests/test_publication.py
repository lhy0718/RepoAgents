from __future__ import annotations

from repoagents.orchestrator import PublicationDraft, PublicationRenderer


def test_publication_renderer_uses_consistent_sections() -> None:
    renderer = PublicationRenderer()
    draft = PublicationDraft(
        issue_id=12,
        issue_title="Improve README quickstart",
        triage_summary="docs issue with low priority",
        plan_summary="Update README and QUICKSTART",
        patch_summary="Added clearer install and test steps.",
        review_summary="approve",
        decision="approve",
        risk_level="low",
        policy_summary="Human approval remains required.",
        changed_files=["README.md", "QUICKSTART.md"],
        test_actions=["Copy/paste the quickstart commands."],
        review_notes=["Docs only change."],
        pr_url="https://github.example/demo/repo/pull/2",
    )

    comment = renderer.render_issue_comment(draft)
    pr_body = renderer.render_pr_body(draft)
    pr_title = renderer.render_pr_title(draft)

    assert "## RepoAgents Run" in comment
    assert "## Summary" in comment
    assert "## Changed Files" in comment
    assert "## Validation" in comment
    assert "## Review Notes" in comment
    assert "## RepoAgents Summary" in pr_body
    assert "## Changed Files" in pr_body
    assert "## Validation" in pr_body
    assert "## Review Notes" in pr_body
    assert pr_title == "RepoAgents: Improve README quickstart (#12)"
