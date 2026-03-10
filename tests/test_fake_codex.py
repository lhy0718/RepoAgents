from __future__ import annotations

import asyncio
from pathlib import Path

from repoagents.backend.base import BackendInvocation
from repoagents.models import EngineeringResult, PlanResult, QAResult, ReviewResult, TriageResult
from repoagents.testing import FakeBackend


def test_fake_backend_triage_surfaces_duplicate_candidates() -> None:
    backend = FakeBackend()
    invocation = BackendInvocation(
        role_name="triage",
        prompt="",
        output_model=TriageResult,
        cwd=Path("/tmp"),
        timeout_seconds=30,
        allow_write=False,
        metadata={
            "issue": {
                "id": 1,
                "title": "Fix empty input crash",
                "body": "Calling parse_items on an empty string should return an empty list.",
                "labels": ["bug"],
                "comments": [],
            },
            "duplicate_candidates_hint": [
                {
                    "issue_id": 7,
                    "title": "Fix crash when parser receives empty input",
                    "score": 0.82,
                    "overlap_terms": ["crash", "empty", "input", "parser"],
                    "labels": ["bug"],
                }
            ],
        },
    )

    result = asyncio.run(backend.run_structured(invocation))

    assert isinstance(result.payload, TriageResult)
    assert result.payload.duplicate_candidates == [
        "#7 confidence=0.82 title=Fix crash when parser receives empty input overlap=crash, empty, input, parser"
    ]
    assert '"duplicate_candidates"' in result.raw_output


def test_fake_backend_engineer_updates_workspace(demo_repo: Path) -> None:
    backend = FakeBackend()
    invocation = BackendInvocation(
        role_name="engineer",
        prompt="",
        output_model=EngineeringResult,
        cwd=demo_repo,
        timeout_seconds=30,
        allow_write=True,
        metadata={
            "issue": {
                "id": 2,
                "title": "Improve README quickstart",
                "body": "Document install and test steps.",
                "labels": ["docs"],
                "comments": [],
            },
            "plan": PlanResult(
                plan_steps=["Edit the README."],
                likely_files=["README.md"],
                risks=[],
                summary="README only",
            ).model_dump(mode="json"),
        },
    )
    result = asyncio.run(backend.run_structured(invocation))
    assert isinstance(result.payload, EngineeringResult)
    assert "README.md" in result.payload.changed_files
    assert '"changed_files"' in result.raw_output
    assert "Quickstart" in (demo_repo / "README.md").read_text(encoding="utf-8")


def test_fake_backend_reviewer_requests_changes_for_code_without_tests() -> None:
    backend = FakeBackend()
    invocation = BackendInvocation(
        role_name="reviewer",
        prompt="",
        output_model=ReviewResult,
        cwd=Path("/tmp"),
        timeout_seconds=30,
        allow_write=False,
        metadata={
            "issue": {
                "id": 1,
                "title": "Fix parser edge case",
                "body": "Parser should handle malformed input.",
                "labels": ["bug"],
                "comments": [],
            },
            "engineering": EngineeringResult(
                changed_files=["src/parser.py"],
                patch_summary="Touched parser logic.",
                test_actions=["Manual smoke test only."],
                summary="Updated one code path.",
            ).model_dump(mode="json"),
            "policy_findings": [],
            "review_signals": {
                "touched_files": ["src/parser.py"],
                "code_files": ["src/parser.py"],
                "test_files": [],
                "out_of_plan_files": [],
                "code_changes_without_tests": True,
                "manual_validation_only": True,
                "risky_change_size": False,
                "summary": "touched=1 code=1 tests=0 missing_test_coverage=true manual_validation_only=true",
            },
        },
    )

    result = asyncio.run(backend.run_structured(invocation))

    assert isinstance(result.payload, ReviewResult)
    assert result.payload.decision.value == "request_changes"
    assert result.payload.risk_level.value == "high"
    assert '"summary"' in result.raw_output
    assert any(
        "without any accompanying test file changes" in note
        for note in result.payload.review_notes
    )


def test_fake_backend_reviewer_requests_changes_for_manual_only_scope_drift() -> None:
    backend = FakeBackend()
    invocation = BackendInvocation(
        role_name="reviewer",
        prompt="",
        output_model=ReviewResult,
        cwd=Path("/tmp"),
        timeout_seconds=30,
        allow_write=False,
        metadata={
            "issue": {
                "id": 1,
                "title": "Refactor parser and auth flow",
                "body": "Refactor internals.",
                "labels": ["feature"],
                "comments": [],
            },
            "engineering": EngineeringResult(
                changed_files=["src/parser.py", "src/auth.py", "tests/test_parser.py"],
                patch_summary="Touched parser and auth flow.",
                test_actions=["Manual smoke test only."],
                summary="Updated two code paths.",
            ).model_dump(mode="json"),
            "policy_findings": [],
            "review_signals": {
                "touched_files": ["src/parser.py", "src/auth.py", "tests/test_parser.py"],
                "code_files": ["src/parser.py", "src/auth.py"],
                "test_files": ["tests/test_parser.py"],
                "out_of_plan_files": ["src/auth.py"],
                "code_changes_without_tests": False,
                "manual_validation_only": True,
                "risky_change_size": False,
                "summary": "touched=3 code=2 tests=1 out_of_plan=1 manual_validation_only=true",
            },
        },
    )

    result = asyncio.run(backend.run_structured(invocation))

    assert result.payload.decision.value == "request_changes"
    assert any("manual-only validation" in note for note in result.payload.review_notes)


def test_fake_backend_qa_role_surfaces_follow_up_when_validation_is_manual_only() -> None:
    backend = FakeBackend()
    invocation = BackendInvocation(
        role_name="qa",
        prompt="",
        output_model=QAResult,
        cwd=Path("/tmp"),
        timeout_seconds=30,
        allow_write=False,
        metadata={
            "issue": {
                "id": 1,
                "title": "Refactor parser",
                "body": "Internal refactor.",
                "labels": ["feature"],
                "comments": [],
            },
            "engineering": EngineeringResult(
                changed_files=["src/parser.py"],
                patch_summary="Refactored parser internals.",
                test_actions=["Manual smoke test only."],
                summary="Updated parser internals.",
            ).model_dump(mode="json"),
            "review_signals": {
                "touched_files": ["src/parser.py"],
                "code_files": ["src/parser.py"],
                "test_files": [],
                "out_of_plan_files": [],
                "code_changes_without_tests": True,
                "manual_validation_only": True,
                "risky_change_size": False,
                "summary": "touched=1 code=1 tests=0 missing_test_coverage=true manual_validation_only=true",
            },
        },
    )

    result = asyncio.run(backend.run_structured(invocation))

    assert result.payload.status.value == "needs_follow_up"
    assert any("manual-only" in gap for gap in result.payload.coverage_gaps)
