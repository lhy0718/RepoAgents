from __future__ import annotations

from repoagents.models import ReviewSignals
from repoagents.roles.review_criteria import evaluate_review_criteria


def test_review_criteria_requires_changes_for_code_without_tests() -> None:
    assessment = evaluate_review_criteria(
        ReviewSignals(
            touched_files=["src/parser.py"],
            code_files=["src/parser.py"],
            test_files=[],
            out_of_plan_files=[],
            code_changes_without_tests=True,
            manual_validation_only=True,
            risky_change_size=False,
            summary="touched=1 code=1 tests=0 missing_test_coverage=true manual_validation_only=true",
        ),
        policy_findings=[],
    )

    assert assessment.decision.value == "request_changes"
    assert assessment.risk_level.value == "high"
    assert "without any accompanying test file changes" in assessment.must_fix[0]


def test_review_criteria_requires_changes_for_manual_only_scope_drift() -> None:
    assessment = evaluate_review_criteria(
        ReviewSignals(
            touched_files=["src/parser.py", "src/auth.py"],
            code_files=["src/parser.py", "src/auth.py"],
            test_files=["tests/test_parser.py"],
            out_of_plan_files=["src/auth.py"],
            code_changes_without_tests=False,
            manual_validation_only=True,
            risky_change_size=False,
            summary="touched=2 code=2 tests=1 out_of_plan=1 manual_validation_only=true",
        ),
        policy_findings=[],
    )

    assert assessment.decision.value == "request_changes"
    assert any("planner shortlist" in note for note in assessment.must_fix)


def test_review_criteria_approves_low_risk_patch_with_watch_items() -> None:
    assessment = evaluate_review_criteria(
        ReviewSignals(
            touched_files=["README.md", "docs/guide.md", "docs/reference.md", "docs/faq.md"],
            code_files=[],
            test_files=[],
            out_of_plan_files=["docs/reference.md"],
            code_changes_without_tests=False,
            manual_validation_only=False,
            risky_change_size=True,
            summary="touched=4 code=0 tests=0 out_of_plan=1 risky_change_size=true",
        ),
        policy_findings=[],
    )

    assert assessment.decision.value == "approve"
    assert assessment.risk_level.value == "medium"
    assert any("closer human inspection" in note for note in assessment.watch_items)


def test_review_criteria_policy_findings_always_block() -> None:
    assessment = evaluate_review_criteria(
        ReviewSignals(summary="touched=0 code=0 tests=0"),
        policy_findings=["Sensitive infra/auth/deploy path requires human review: .github/workflows/release.yml"],
    )

    assert assessment.decision.value == "request_changes"
    assert assessment.must_fix == [
        "Sensitive infra/auth/deploy path requires human review: .github/workflows/release.yml"
    ]
