from __future__ import annotations

from pathlib import Path

from repoagents.config import load_config
from repoagents.models import PlanResult, QAResult, ReviewResult, TriageResult
from repoagents.prompts import PromptRenderer
from repoagents.utils import build_repo_context


def test_prompt_rendering_includes_schema_and_policy(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    renderer = PromptRenderer(loaded)
    prompt = renderer.render(
        "planner",
        PlanResult,
        {
            "issue": {"title": "Improve README quickstart", "body": "Add commands.", "labels": ["docs"]},
            "issue_json": "{}",
            "issue_comments_excerpt": "No recent comments.",
            "repo_context": "Repository files:\n- README.md",
            "triage_result_json": "{}",
            "plan_result_json": "{}",
            "engineering_result_json": "{}",
            "diff_report_json": "{}",
            "policy_findings_json": "[]",
            "dry_run": True,
        },
    )
    assert "Scope Policy" in prompt
    assert "Return JSON only" in prompt
    assert '"properties"' in prompt


def test_triage_prompt_rendering_includes_duplicate_candidates_context(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    renderer = PromptRenderer(loaded)
    prompt = renderer.render(
        "triage",
        TriageResult,
        {
            "issue": {"title": "Fix empty input crash", "body": "Parser crashes.", "labels": ["bug"]},
            "issue_json": "{}",
            "issue_comments_excerpt": "No recent comments.",
            "repo_context": "Repository context",
            "duplicate_candidates_context": "- #12 score=0.83 title=Fix crash when parser receives empty input labels=bug overlap=crash, empty, input",
            "duplicate_candidates_json": "[]",
            "triage_result_json": "{}",
            "plan_result_json": "{}",
            "engineering_result_json": "{}",
            "diff_report_json": "{}",
            "review_signals_json": "{}",
            "policy_findings_json": "[]",
            "dry_run": True,
        },
    )

    assert "Similar open issues to check for duplicates:" in prompt
    assert "#12 score=0.83" in prompt


def test_reviewer_prompt_rendering_includes_review_signals(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    renderer = PromptRenderer(loaded)
    prompt = renderer.render(
        "reviewer",
        ReviewResult,
        {
            "issue": {"title": "Fix empty input crash", "body": "Add guard.", "labels": ["bug"]},
            "issue_json": "{}",
            "issue_comments_excerpt": "No recent comments.",
            "repo_context": "Repository files:\n- parser.py\n- tests/test_parser.py",
            "triage_result_json": "{}",
            "plan_result_json": '{"likely_files":["parser.py"]}',
            "engineering_result_json": '{"changed_files":["parser.py"]}',
            "diff_report_json": '{"changed_files":["parser.py"]}',
            "review_signals_json": '{"code_changes_without_tests":true}',
            "review_criteria_json": '{"decision":"request_changes","must_fix":["Code paths changed without any accompanying test file changes."]}',
            "extra_role_results_json": '{"qa":{"status":"needs_follow_up"}}',
            "policy_findings_json": "[]",
            "dry_run": False,
        },
    )
    assert "Planner result:" in prompt
    assert "Review signals:" in prompt
    assert "RepoAgents review criteria:" in prompt
    assert "Extra role results:" in prompt
    assert "must_fix" in prompt
    assert "code_changes_without_tests" in prompt


def test_planner_prompt_rendering_includes_richer_repo_context(demo_git_repo: Path) -> None:
    loaded = load_config(demo_git_repo)
    renderer = PromptRenderer(loaded)
    prompt = renderer.render(
        "planner",
        PlanResult,
        {
            "issue": {"title": "Fix empty input crash", "body": "Handle empty strings.", "labels": ["bug"]},
            "issue_json": "{}",
            "issue_comments_excerpt": "No recent comments.",
            "repo_context": build_repo_context(demo_git_repo),
            "triage_result_json": "{}",
            "plan_result_json": "{}",
            "engineering_result_json": "{}",
            "diff_report_json": "{}",
            "review_signals_json": "{}",
            "policy_findings_json": "[]",
            "dry_run": False,
        },
    )

    assert "Top-level directories:" in prompt
    assert "Test layout:" in prompt
    assert "Recent git changes:" in prompt


def test_qa_prompt_rendering_includes_engineering_and_diff_context(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    renderer = PromptRenderer(loaded)
    prompt = renderer.render(
        "qa",
        QAResult,
        {
            "issue": {"title": "Refactor parser", "body": "Refactor internals.", "labels": ["feature"]},
            "issue_json": "{}",
            "issue_comments_excerpt": "No recent comments.",
            "repo_context": "Repository context",
            "duplicate_candidates_context": "- none",
            "duplicate_candidates_json": "[]",
            "extra_role_results_json": "{}",
            "triage_result_json": '{"issue_type":"feature"}',
            "plan_result_json": '{"likely_files":["src/parser.py"]}',
            "engineering_result_json": '{"changed_files":["src/parser.py"],"test_actions":["Manual smoke test only."]}',
            "diff_report_json": '{"changed_files":["src/parser.py"]}',
            "review_signals_json": '{"manual_validation_only":true}',
            "review_criteria_json": '{"decision":"request_changes"}',
            "policy_findings_json": "[]",
            "dry_run": False,
        },
    )

    assert "You are RepoAgents's `qa` role." in prompt
    assert "Engineering result:" in prompt
    assert "Diff report:" in prompt
