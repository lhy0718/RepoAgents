from __future__ import annotations

from repoagents.models import DiffReport, EngineeringResult, PlanResult
from repoagents.roles.review_signals import build_review_signals


def test_review_signals_identify_missing_tests_and_scope_drift() -> None:
    signals = build_review_signals(
        PlanResult(
            plan_steps=["Edit parser."],
            likely_files=["src/parser.py"],
            risks=[],
            summary="parser only",
        ),
        EngineeringResult(
            changed_files=["src/parser.py", "src/auth.py"],
            patch_summary="Updated parser and auth flow.",
            test_actions=["Manual smoke test only."],
            summary="Touched two code files.",
        ),
        DiffReport(
            changed_files=["src/parser.py", "src/auth.py"],
            total_added_lines=40,
            total_removed_lines=8,
            summary="changed=2 added=0 removed=0 +40/-8",
        ),
    )

    assert signals.code_files == ["src/parser.py", "src/auth.py"]
    assert signals.test_files == []
    assert signals.code_changes_without_tests is True
    assert signals.manual_validation_only is True
    assert signals.out_of_plan_files == ["src/auth.py"]
    assert "missing_test_coverage=true" in signals.summary
