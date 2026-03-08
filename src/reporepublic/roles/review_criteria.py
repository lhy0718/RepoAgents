from __future__ import annotations

from dataclasses import dataclass

from reporepublic.models import ReviewDecision, ReviewSignals, RiskLevel


@dataclass(slots=True)
class ReviewCriteriaAssessment:
    decision: ReviewDecision
    risk_level: RiskLevel
    must_fix: list[str]
    watch_items: list[str]
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision.value,
            "risk_level": self.risk_level.value,
            "must_fix": self.must_fix,
            "watch_items": self.watch_items,
            "summary": self.summary,
        }


def evaluate_review_criteria(
    review_signals: ReviewSignals,
    policy_findings: list[str],
) -> ReviewCriteriaAssessment:
    must_fix: list[str] = []
    watch_items: list[str] = []
    out_of_plan_code_files = [
        path for path in review_signals.out_of_plan_files if path in review_signals.code_files
    ]

    must_fix.extend(policy_findings)

    if review_signals.code_changes_without_tests:
        must_fix.append("Code paths changed without any accompanying test file changes.")

    if review_signals.code_files and review_signals.manual_validation_only and review_signals.risky_change_size:
        must_fix.append("Code change is broad enough that manual-only validation is not sufficient.")

    if review_signals.code_files and review_signals.manual_validation_only and out_of_plan_code_files:
        joined = ", ".join(out_of_plan_code_files[:3])
        must_fix.append(
            f"Code change left the planner shortlist and still relies on manual-only validation: {joined}"
        )

    if len(out_of_plan_code_files) >= 2:
        joined = ", ".join(out_of_plan_code_files[:3])
        must_fix.append(f"Patch touched multiple code files outside the planner shortlist: {joined}")

    if review_signals.out_of_plan_files:
        joined = ", ".join(review_signals.out_of_plan_files[:3])
        watch_items.append(f"Patch touched files outside the planner shortlist: {joined}")

    if review_signals.risky_change_size:
        watch_items.append("Patch size is large enough to justify closer human inspection.")

    if review_signals.manual_validation_only and review_signals.code_files and not _has_manual_validation_blocker(must_fix):
        watch_items.append(
            "Code changed but validation remains manual-only; add focused automated tests if possible."
        )

    must_fix = _ordered_unique(must_fix)
    watch_items = _ordered_unique(
        [item for item in watch_items if item not in must_fix]
    )

    if must_fix:
        decision = ReviewDecision.REQUEST_CHANGES
        risk_level = RiskLevel.HIGH
    elif watch_items:
        decision = ReviewDecision.APPROVE
        risk_level = RiskLevel.MEDIUM
    else:
        decision = ReviewDecision.APPROVE
        risk_level = RiskLevel.LOW

    summary = (
        f"decision={decision.value} risk={risk_level.value} "
        f"must_fix={len(must_fix)} watch_items={len(watch_items)}"
    )
    return ReviewCriteriaAssessment(
        decision=decision,
        risk_level=risk_level,
        must_fix=must_fix,
        watch_items=watch_items,
        summary=summary,
    )


def risk_rank(level: RiskLevel) -> int:
    order = {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
    }
    return order[level]


def _has_manual_validation_blocker(must_fix: list[str]) -> bool:
    return any("manual-only validation" in item or "manual-only" in item for item in must_fix)


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
