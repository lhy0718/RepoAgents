from __future__ import annotations

import argparse
import json
import os
import re
import stat
from pathlib import Path

from repoagents.backend.base import BackendInvocation, BackendRunResult, BackendRunner
from repoagents.models import (
    EngineeringResult,
    IssueRef,
    IssueType,
    PlanResult,
    Priority,
    QAResult,
    QAStatus,
    ReviewSignals,
    ReviewDecision,
    ReviewResult,
    RiskLevel,
    TriageResult,
)
from repoagents.roles.review_criteria import evaluate_review_criteria


class FakeBackend(BackendRunner):
    async def run_structured(self, invocation: BackendInvocation) -> BackendRunResult:
        payload = build_fake_payload(
            role_name=invocation.role_name,
            issue=IssueRef.model_validate(invocation.metadata["issue"]),
            workspace=invocation.cwd,
            duplicate_candidates_hint=invocation.metadata.get("duplicate_candidates_hint", []),
            triage_payload=invocation.metadata.get("triage"),
            plan_payload=invocation.metadata.get("plan"),
            engineering_payload=invocation.metadata.get("engineering"),
            review_signals_payload=invocation.metadata.get("review_signals"),
            policy_findings=invocation.metadata.get("policy_findings", []),
            repo_context=str(invocation.metadata.get("repo_context", "")),
        )
        return BackendRunResult(payload=payload, raw_output=payload.model_dump_json(indent=2))


def build_fake_payload(
    *,
    role_name: str,
    issue: IssueRef,
    workspace: Path,
    duplicate_candidates_hint: list[dict[str, object]] | None = None,
    triage_payload: dict[str, object] | None = None,
    plan_payload: dict[str, object] | None = None,
    engineering_payload: dict[str, object] | None = None,
    review_signals_payload: dict[str, object] | None = None,
    policy_findings: list[str] | None = None,
    repo_context: str = "",
) -> TriageResult | PlanResult | EngineeringResult | QAResult | ReviewResult:
    duplicate_candidates_hint = duplicate_candidates_hint or []
    policy_findings = policy_findings or []

    if role_name == "triage":
        return _triage(issue, duplicate_candidates_hint)
    if role_name == "planner":
        triage = TriageResult.model_validate(triage_payload or {})
        return _planner(issue, triage, repo_context)
    if role_name == "engineer":
        plan = PlanResult.model_validate(plan_payload or {})
        return _engineer(issue, plan, workspace)
    if role_name == "qa":
        engineering = EngineeringResult.model_validate(engineering_payload or {})
        review_signals = ReviewSignals.model_validate(review_signals_payload or {})
        return _qa(issue, engineering, review_signals)
    if role_name == "reviewer":
        engineering = EngineeringResult.model_validate(engineering_payload or {})
        review_signals = ReviewSignals.model_validate(review_signals_payload or {})
        return _review(issue, engineering, policy_findings, review_signals)
    raise ValueError(f"Unsupported fake Codex role: {role_name}")


def install_fake_codex_shim(target: Path, *, project_root: Path | None = None) -> Path:
    root = (project_root or Path(__file__).resolve().parents[3]).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f'ROOT_DIR="{root}"',
                'exec uv run --project "$ROOT_DIR" python -m repoagents.testing.fake_codex "$@"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic fake Codex CLI for tests and demos.")
    parser.add_argument("--install-shim", type=Path, help="Write a shell shim that re-invokes this module.")
    parser.add_argument("--project-root", type=Path, help="Repo root used by --install-shim.")
    parser.add_argument("args", nargs="*")
    parsed, passthrough = parser.parse_known_args(argv)

    if parsed.install_shim is not None:
        install_fake_codex_shim(parsed.install_shim, project_root=parsed.project_root)
        print(parsed.install_shim)
        return 0

    command_args = [*parsed.args, *passthrough]
    if command_args == ["--version"]:
        print("codex fake-cli 0.0.0")
        return 0
    return _run_cli(command_args)


def _run_cli(argv: list[str]) -> int:
    output_path: Path | None = None
    for index, item in enumerate(argv):
        if item == "-o" and index + 1 < len(argv):
            output_path = Path(argv[index + 1])
            break
    if output_path is None:
        raise SystemExit("fake codex expected -o <output-path>")

    prompt = os.fdopen(0, encoding="utf-8").read()
    payload = build_fake_payload_from_prompt(prompt, workspace=Path.cwd())
    output_path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    return 0


def build_fake_payload_from_prompt(
    prompt: str,
    *,
    workspace: Path,
) -> TriageResult | PlanResult | EngineeringResult | QAResult | ReviewResult:
    role_name = _parse_role_name(prompt)
    if role_name == "triage":
        return _triage(_parse_triage_issue(prompt), [])
    if role_name == "planner":
        issue = IssueRef.model_validate(_extract_json_block(prompt, "Issue:"))
        triage = TriageResult.model_validate(_extract_json_block(prompt, "Triage result:"))
        return _planner(issue, triage, _extract_text_block(prompt, "Repository context:", "Return JSON only"))
    if role_name == "engineer":
        issue = IssueRef.model_validate(_extract_json_block(prompt, "Issue:"))
        plan = PlanResult.model_validate(_extract_json_block(prompt, "Plan result:"))
        return _engineer(issue, plan, workspace)
    if role_name == "qa":
        issue = IssueRef.model_validate(_extract_json_block(prompt, "Issue:"))
        engineering = EngineeringResult.model_validate(_extract_json_block(prompt, "Engineering result:"))
        review_signals = ReviewSignals.model_validate(_extract_json_block(prompt, "Review signals:"))
        return _qa(issue, engineering, review_signals)
    if role_name == "reviewer":
        issue = IssueRef.model_validate(_extract_json_block(prompt, "Issue:"))
        engineering = EngineeringResult.model_validate(_extract_json_block(prompt, "Engineering result:"))
        review_signals = ReviewSignals.model_validate(_extract_json_block(prompt, "Review signals:"))
        policy_findings = _extract_json_block(prompt, "Policy findings:")
        return _review(issue, engineering, list(policy_findings), review_signals)
    raise ValueError(f"Unsupported fake Codex role: {role_name}")


def _parse_role_name(prompt: str) -> str:
    first_line = prompt.splitlines()[0].strip()
    match = re.search(r"`([^`]+)`", first_line)
    if match is None:
        raise ValueError("Unable to determine fake Codex role from prompt.")
    return match.group(1)


def _parse_triage_issue(prompt: str) -> IssueRef:
    title = ""
    for line in prompt.splitlines():
        if line.startswith("- title: "):
            title = line.removeprefix("- title: ").strip()
            break
    body = _extract_text_block(prompt, "Issue body:", "Return JSON only")
    return IssueRef(id=1, number=1, title=title or "Synthetic issue", body=body)


def _extract_json_block(prompt: str, heading: str) -> object:
    marker = f"{heading}\n"
    start = prompt.find(marker)
    if start == -1:
        raise ValueError(f"Missing heading in fake Codex prompt: {heading}")
    decoder = json.JSONDecoder()
    payload, _ = decoder.raw_decode(prompt[start + len(marker) :].lstrip())
    return payload


def _extract_text_block(prompt: str, heading: str, terminator: str) -> str:
    marker = f"{heading}\n"
    start = prompt.find(marker)
    if start == -1:
        return ""
    content_start = start + len(marker)
    end = prompt.find(terminator, content_start)
    if end == -1:
        end = len(prompt)
    return prompt[content_start:end].strip()


def _triage(issue: IssueRef, duplicate_candidates_hint: list[dict[str, object]]) -> TriageResult:
    haystack = f"{issue.title}\n{issue.body}".lower()
    if any(keyword in haystack for keyword in ("readme", "docs", "quickstart")):
        issue_type = IssueType.DOCS
        priority = Priority.LOW
    elif any(keyword in haystack for keyword in ("crash", "error", "bug", "fix")):
        issue_type = IssueType.BUG
        priority = Priority.HIGH if "crash" in haystack else Priority.MEDIUM
    elif "feature" in haystack or "add" in haystack:
        issue_type = IssueType.FEATURE
        priority = Priority.MEDIUM
    else:
        issue_type = IssueType.CHORE
        priority = Priority.MEDIUM
    duplicates = _format_duplicate_candidates(duplicate_candidates_hint)
    if "duplicate" in haystack and not duplicates:
        duplicates.append("Possible duplicate mentioned in issue body.")
    return TriageResult(
        issue_type=issue_type,
        priority=priority,
        duplicate_candidates=duplicates,
        summary=(
            f"{issue_type.value} issue with {priority.value} priority based on title/body heuristics."
            f" Duplicate candidates found: {len(duplicates)}."
        ),
    )


def _planner(issue: IssueRef, triage: TriageResult, repo_context: str) -> PlanResult:
    likely_files = _guess_files(issue, triage, repo_context)
    steps = [
        "Inspect the current implementation and reproduce the issue in the isolated workspace.",
        "Make the smallest safe change that resolves the issue while following RepoAgents policies.",
        "Run or describe focused validation steps and summarize risks for human approval.",
    ]
    risks = ["Human approval remains required before merge."]
    if triage.issue_type == IssueType.BUG:
        risks.insert(0, "Behavioral regressions are possible if the fix changes parsing logic.")
    elif triage.issue_type == IssueType.DOCS:
        risks.insert(0, "Docs drift is possible if examples do not match runtime behavior.")
    return PlanResult(
        plan_steps=steps,
        likely_files=likely_files,
        risks=risks,
        summary=f"Plan prepared for {triage.issue_type.value} work across {', '.join(likely_files)}.",
    )


def _engineer(issue: IssueRef, plan: PlanResult, workspace: Path) -> EngineeringResult:
    changed_files: list[str] = []
    haystack = f"{issue.title}\n{issue.body}".lower()
    if any(keyword in haystack for keyword in ("readme", "docs", "quickstart")):
        target = _first_existing(workspace, ["README.md", "docs/README.md"])
        if target is None:
            target = workspace / "README.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# Project\n", encoding="utf-8")
        current = target.read_text(encoding="utf-8", errors="ignore")
        if "## Quickstart" not in current:
            current = current.rstrip() + "\n\n## Quickstart\n\n1. Install dependencies.\n2. Run the test suite.\n"
        else:
            current = current.rstrip() + "\n\n- RepoAgents verified the quickstart instructions.\n"
        target.write_text(current, encoding="utf-8")
        changed_files.append(target.relative_to(workspace).as_posix())
        test_actions = ["No code tests required; validate Markdown rendering and commands manually."]
    elif "empty input" in haystack or "crash" in haystack:
        target = _first_existing(workspace, plan.likely_files + ["src/parser.py", "parser.py"])
        if target is None:
            target = workspace / "src" / "parser.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "def parse_items(raw: str) -> list[str]:\n    return [part.strip() for part in raw.split(',')]\n",
                encoding="utf-8",
            )
        original = target.read_text(encoding="utf-8", errors="ignore")
        if "if not raw.strip()" not in original and "def " in original:
            lines = original.splitlines()
            updated: list[str] = []
            inserted = False
            for line in lines:
                updated.append(line)
                if not inserted and line.startswith("def "):
                    updated.append("    if not raw.strip():")
                    updated.append("        return []")
                    inserted = True
            target.write_text("\n".join(updated) + "\n", encoding="utf-8")
        changed_files.append(target.relative_to(workspace).as_posix())
        test_target = workspace / "tests" / "test_empty_input.py"
        test_target.parent.mkdir(parents=True, exist_ok=True)
        test_target.write_text(
            "from parser import parse_items\n\n\ndef test_empty_input_returns_empty_list():\n    assert parse_items('') == []\n",
            encoding="utf-8",
        )
        changed_files.append(test_target.relative_to(workspace).as_posix())
        test_actions = ["Run the parser unit tests covering empty input handling."]
    else:
        target = _first_existing(workspace, plan.likely_files + ["tests/test_generated.py"])
        if target is None:
            target = workspace / "tests" / "test_generated.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "def test_repoagents_generated_placeholder():\n    assert True\n",
            encoding="utf-8",
        )
        changed_files.append(target.relative_to(workspace).as_posix())
        test_actions = ["Run the focused tests for the generated change."]

    return EngineeringResult(
        changed_files=changed_files,
        patch_summary=f"Applied deterministic fake Codex changes for issue '{issue.title}'.",
        test_actions=test_actions,
        summary=f"Updated {len(changed_files)} file(s) in the isolated workspace.",
    )


def _review(
    issue: IssueRef,
    engineering: EngineeringResult,
    policy_findings: list[str],
    review_signals: ReviewSignals,
) -> ReviewResult:
    criteria = evaluate_review_criteria(review_signals, policy_findings)
    notes = [
        "Human approval is still required before merge.",
        f"Diff review summary: {review_signals.summary}",
    ]
    notes.extend(criteria.must_fix)
    notes.extend(criteria.watch_items)
    if criteria.risk_level == RiskLevel.LOW:
        notes.append(f"Patch for '{issue.title}' is small and easy to inspect.")

    return ReviewResult(
        decision=criteria.decision,
        risk_level=criteria.risk_level,
        review_notes=_ordered_unique(notes),
        summary=f"Reviewer decision: {criteria.decision.value} with {criteria.risk_level.value} risk.",
    )


def _qa(
    issue: IssueRef,
    engineering: EngineeringResult,
    review_signals: ReviewSignals,
) -> QAResult:
    recommended_commands = _normalize_test_commands(engineering.test_actions)
    coverage_gaps: list[str] = []
    status = QAStatus.PASS

    if review_signals.code_changes_without_tests:
        status = QAStatus.NEEDS_FOLLOW_UP
        coverage_gaps.append("Code changed without any test file updates.")
    if review_signals.manual_validation_only and review_signals.code_files:
        status = QAStatus.NEEDS_FOLLOW_UP
        coverage_gaps.append("Validation remains manual-only for a code change.")
    if review_signals.out_of_plan_files:
        joined = ", ".join(review_signals.out_of_plan_files[:3])
        coverage_gaps.append(f"Files outside the planner shortlist need focused regression checks: {joined}")
    if not recommended_commands:
        recommended_commands = ["pytest -q"]

    return QAResult(
        status=status,
        recommended_commands=recommended_commands,
        coverage_gaps=coverage_gaps,
        summary=f"QA status for '{issue.title}': {status.value}.",
    )


def _first_existing(workspace: Path, candidates: list[str]) -> Path | None:
    for candidate in candidates:
        path = workspace / candidate
        if path.exists():
            return path
    return None


def _guess_files(issue: IssueRef, triage: TriageResult, repo_context: str) -> list[str]:
    haystack = f"{issue.title}\n{issue.body}\n{repo_context}".lower()
    if triage.issue_type == IssueType.DOCS:
        return ["README.md", "QUICKSTART.md"]
    if "parser" in haystack:
        return ["src/parser.py", "tests/test_parser.py"]
    if "web" in haystack or "frontend" in haystack:
        return ["src/app.js", "README.md"]
    return ["README.md", "tests/test_generated.py"]


def _format_duplicate_candidates(duplicate_candidates_hint: list[dict[str, object]]) -> list[str]:
    duplicates: list[str] = []
    for candidate in duplicate_candidates_hint:
        issue_id = candidate.get("issue_id")
        title = str(candidate.get("title", "")).strip()
        score = float(candidate.get("score", 0.0))
        overlap_terms = candidate.get("overlap_terms", [])
        if isinstance(overlap_terms, list):
            overlap = ", ".join(str(term) for term in overlap_terms[:4]) or "weak lexical overlap"
        else:
            overlap = "weak lexical overlap"
        duplicates.append(f"#{issue_id} confidence={score:.2f} title={title} overlap={overlap}")
    return duplicates


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _normalize_test_commands(test_actions: list[str]) -> list[str]:
    commands: list[str] = []
    for action in test_actions:
        lowered = action.lower()
        if lowered.startswith("run ") or "pytest" in lowered:
            commands.append(action)
    return _ordered_unique(commands)


if __name__ == "__main__":
    raise SystemExit(main())
