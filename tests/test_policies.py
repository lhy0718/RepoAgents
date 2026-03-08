from __future__ import annotations

from reporepublic.models import DiffReport, IssueType, PublicationMode
from reporepublic.policies import PolicyRules, evaluate_policy


def test_policy_blocks_secret_like_file_changes() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.BUG,
        diff_report=DiffReport(
            changed_files=[".env"],
            summary="changed=1 added=0 removed=0 +1/-1",
        ),
        allowed_auto_merge_types=["docs", "tests"],
    )

    assert evaluation.blocked is True
    assert evaluation.auto_merge_candidate is False
    assert evaluation.publication_mode == PublicationMode.COMMENT_ONLY
    assert any("Sensitive secret-like file change blocked" in finding for finding in evaluation.findings)
    assert evaluation.summary == "Policy violations detected; reviewer must request changes."


def test_policy_blocks_ci_cd_changes() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.CHORE,
        diff_report=DiffReport(
            changed_files=[".github/workflows/republic-check.yml"],
            summary="changed=1 added=0 removed=0 +4/-1",
        ),
        allowed_auto_merge_types=["docs", "tests"],
    )

    assert evaluation.blocked is True
    assert any(
        "Sensitive infra/auth/deploy path requires human review" in finding
        for finding in evaluation.findings
    )


def test_policy_blocks_auth_sensitive_file_changes() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.FEATURE,
        diff_report=DiffReport(
            changed_files=["src/auth_manager.py"],
            summary="changed=1 added=0 removed=0 +10/-2",
        ),
        allowed_auto_merge_types=["docs", "tests"],
    )

    assert evaluation.blocked is True
    assert any(
        "Sensitive infra/auth/deploy path requires human review" in finding
        for finding in evaluation.findings
    )


def test_policy_blocks_large_deletions() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.CHORE,
        diff_report=DiffReport(
            changed_files=["src/parser.py"],
            total_removed_lines=250,
            summary="changed=1 added=0 removed=0 +5/-250",
        ),
        allowed_auto_merge_types=["docs", "tests"],
    )

    assert evaluation.blocked is True
    assert any("Large deletion detected" in finding for finding in evaluation.findings)


def test_policy_marks_docs_only_changes_as_auto_merge_candidates() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.DOCS,
        diff_report=DiffReport(
            changed_files=["README.md", "docs/architecture.md"],
            total_added_lines=12,
            total_removed_lines=3,
            summary="changed=2 added=0 removed=0 +12/-3",
        ),
        allowed_auto_merge_types=["docs", "tests"],
    )

    assert evaluation.blocked is False
    assert evaluation.auto_merge_candidate is True
    assert evaluation.publication_mode == PublicationMode.HUMAN_APPROVAL
    assert evaluation.findings == []
    assert evaluation.summary == "Human approval remains required before publishing changes."


def test_policy_can_limit_low_risk_changes_to_comment_only() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.DOCS,
        diff_report=DiffReport(
            changed_files=["README.md"],
            total_added_lines=4,
            total_removed_lines=1,
            summary="changed=1 added=0 removed=0 +4/-1",
        ),
        allowed_auto_merge_types=["docs", "tests"],
        requested_publication_mode=PublicationMode.COMMENT_ONLY,
    )

    assert evaluation.blocked is False
    assert evaluation.auto_merge_candidate is True
    assert evaluation.publication_mode == PublicationMode.COMMENT_ONLY
    assert evaluation.summary == "Low-risk docs/tests change is limited to comment-only publication."


def test_policy_can_allow_low_risk_changes_to_publish_as_draft_pr() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.DOCS,
        diff_report=DiffReport(
            changed_files=["README.md"],
            total_added_lines=5,
            total_removed_lines=0,
            summary="changed=1 added=0 removed=0 +5/-0",
        ),
        allowed_auto_merge_types=["docs", "tests"],
        requested_publication_mode=PublicationMode.DRAFT_PR,
    )

    assert evaluation.blocked is False
    assert evaluation.auto_merge_candidate is True
    assert evaluation.publication_mode == PublicationMode.DRAFT_PR
    assert evaluation.summary == "Low-risk docs/tests change may open a draft PR when writes are enabled."


def test_policy_keeps_non_low_risk_changes_on_human_approval_path() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.BUG,
        diff_report=DiffReport(
            changed_files=["src/parser.py"],
            total_added_lines=8,
            total_removed_lines=2,
            summary="changed=1 added=0 removed=0 +8/-2",
        ),
        allowed_auto_merge_types=["docs", "tests"],
        requested_publication_mode=PublicationMode.COMMENT_ONLY,
    )

    assert evaluation.blocked is False
    assert evaluation.auto_merge_candidate is False
    assert evaluation.publication_mode == PublicationMode.HUMAN_APPROVAL
    assert evaluation.summary == "Human approval remains required before publishing changes."


def test_policy_blocks_sensitive_infra_paths() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.CHORE,
        diff_report=DiffReport(
            changed_files=["infra/terraform/main.tf"],
            summary="changed=1 added=0 removed=0 +12/-1",
        ),
        allowed_auto_merge_types=["docs", "tests"],
    )

    assert evaluation.blocked is True
    assert any("Sensitive infra/auth/deploy path requires human review" in finding for finding in evaluation.findings)


def test_policy_supports_repo_specific_sensitive_path_rules() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.FEATURE,
        diff_report=DiffReport(
            changed_files=["custom-infra/policies.yaml"],
            summary="changed=1 added=0 removed=0 +4/-1",
        ),
        allowed_auto_merge_types=["docs", "tests"],
        rules=PolicyRules(sensitive_path_prefixes=["custom-infra/"]),
    )

    assert evaluation.blocked is True
    assert any("custom-infra/policies.yaml" in finding for finding in evaluation.findings)


def test_policy_ignores_large_deletions_in_generated_and_vendor_paths() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.CHORE,
        diff_report=DiffReport(
            removed_files=["vendor/bundle.js", "generated/openapi.json"],
            total_removed_lines=600,
            summary="changed=0 added=0 removed=2 +0/-600",
        ),
        allowed_auto_merge_types=["docs", "tests"],
    )

    assert evaluation.blocked is False
    assert not any("Large deletion detected" in finding for finding in evaluation.findings)


def test_policy_treats_remove_plus_add_same_filename_as_move_not_large_deletion() -> None:
    evaluation = evaluate_policy(
        issue_type=IssueType.CHORE,
        diff_report=DiffReport(
            added_files=["lib/parser.py"],
            removed_files=["src/parser.py"],
            total_removed_lines=350,
            summary="changed=0 added=1 removed=1 +350/-350",
        ),
        allowed_auto_merge_types=["docs", "tests"],
    )

    assert evaluation.blocked is False
    assert not any("Large deletion detected" in finding for finding in evaluation.findings)
