from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PublicationDraft:
    issue_id: int
    issue_title: str
    triage_summary: str
    plan_summary: str
    patch_summary: str
    review_summary: str
    decision: str
    risk_level: str
    policy_summary: str
    changed_files: list[str] = field(default_factory=list)
    test_actions: list[str] = field(default_factory=list)
    review_notes: list[str] = field(default_factory=list)
    pr_url: str | None = None
    preview_only: bool = False


class PublicationRenderer:
    def render_issue_comment(self, draft: PublicationDraft) -> str:
        lines = [
            "## RepoAgents Run",
            f"- Issue: #{draft.issue_id} {draft.issue_title}",
            f"- Decision: `{draft.decision}`",
            f"- Risk: `{draft.risk_level}`",
            f"- Policy: {draft.policy_summary}",
        ]
        if draft.pr_url:
            lines.append(f"- Draft PR: {draft.pr_url}")
        if draft.preview_only:
            lines.append("- Mode: preview only; engineer/reviewer steps were not executed.")
        lines.extend(
            [
                "",
                "## Summary",
                f"- Triage: {draft.triage_summary}",
                f"- Plan: {draft.plan_summary}",
                f"- Patch: {draft.patch_summary}",
                f"- Review: {draft.review_summary}",
                "",
                "## Changed Files",
                *self._bullet_list(draft.changed_files),
                "",
                "## Validation",
                *self._bullet_list(draft.test_actions),
                "",
                "## Review Notes",
                *self._bullet_list(draft.review_notes),
                "",
                "Human approval is still required before merge.",
            ]
        )
        return "\n".join(lines)

    def render_pr_title(self, draft: PublicationDraft) -> str:
        return f"RepoAgents: {draft.issue_title} (#{draft.issue_id})"

    def render_pr_body(self, draft: PublicationDraft) -> str:
        lines = [
            "## Issue",
            f"- #{draft.issue_id}: {draft.issue_title}",
            "",
            "## RepoAgents Summary",
            f"- Triage: {draft.triage_summary}",
            f"- Plan: {draft.plan_summary}",
            f"- Patch: {draft.patch_summary}",
            f"- Review: {draft.review_summary}",
            f"- Decision: `{draft.decision}`",
            f"- Risk: `{draft.risk_level}`",
            f"- Policy: {draft.policy_summary}",
        ]
        if draft.preview_only:
            lines.extend(
                [
                    "",
                    "> Preview only. Engineer and reviewer outputs were not executed in dry-run mode.",
                ]
            )
        lines.extend(
            [
                "",
                "## Changed Files",
                *self._bullet_list(draft.changed_files),
                "",
                "## Validation",
                *self._bullet_list(draft.test_actions),
                "",
                "## Review Notes",
                *self._bullet_list(draft.review_notes),
                "",
                "Human approval is required before merge.",
            ]
        )
        return "\n".join(lines)

    def build_preview_draft(
        self,
        issue_id: int,
        issue_title: str,
        triage_summary: str,
        plan_summary: str,
        likely_files: list[str],
        policy_summary: str,
    ) -> PublicationDraft:
        return PublicationDraft(
            issue_id=issue_id,
            issue_title=issue_title,
            triage_summary=triage_summary,
            plan_summary=plan_summary,
            patch_summary="Preview only. Engineer step has not executed yet.",
            review_summary="Preview only. Reviewer step has not executed yet.",
            decision="preview",
            risk_level="preview",
            policy_summary=policy_summary,
            changed_files=likely_files,
            test_actions=["Preview only. Validation actions will be finalized after engineer output."],
            review_notes=["Preview only. Final review notes depend on the realized diff."],
            preview_only=True,
        )

    def _bullet_list(self, items: list[str]) -> list[str]:
        if not items:
            return ["- none"]
        return [f"- {item}" for item in items]
