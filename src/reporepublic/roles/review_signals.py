from __future__ import annotations

from pathlib import PurePosixPath

from reporepublic.models import DiffReport, EngineeringResult, PlanResult, ReviewSignals


def build_review_signals(
    plan: PlanResult | None,
    engineering: EngineeringResult | None,
    diff_report: DiffReport | None,
) -> ReviewSignals:
    touched_files = _ordered_unique(
        [
            *(diff_report.changed_files if diff_report else []),
            *(diff_report.added_files if diff_report else []),
            *(diff_report.removed_files if diff_report else []),
            *(engineering.changed_files if engineering else []),
        ]
    )
    test_files = [path for path in touched_files if _is_test_file(path)]
    code_files = [path for path in touched_files if _is_code_file(path)]
    likely_files = set(plan.likely_files if plan else [])
    out_of_plan_files = [
        path
        for path in touched_files
        if likely_files and path not in likely_files and not _matches_likely_path(path, likely_files)
    ]
    manual_validation_only = _has_manual_only_validation(engineering)
    code_changes_without_tests = bool(code_files) and not test_files
    risky_change_size = bool(diff_report) and (
        len(touched_files) >= 4
        or diff_report.total_added_lines >= 120
        or diff_report.total_removed_lines >= 120
    )
    return ReviewSignals(
        touched_files=touched_files,
        code_files=code_files,
        test_files=test_files,
        out_of_plan_files=out_of_plan_files,
        code_changes_without_tests=code_changes_without_tests,
        manual_validation_only=manual_validation_only,
        risky_change_size=risky_change_size,
        summary=_build_summary(
            touched_files=touched_files,
            code_files=code_files,
            test_files=test_files,
            out_of_plan_files=out_of_plan_files,
            code_changes_without_tests=code_changes_without_tests,
            manual_validation_only=manual_validation_only,
            risky_change_size=risky_change_size,
        ),
    )


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _is_test_file(path: str) -> bool:
    normalized = path.lower()
    return normalized.startswith("tests/") or "/tests/" in normalized or normalized.endswith("_test.py")


def _is_code_file(path: str) -> bool:
    pure = PurePosixPath(path)
    if _is_test_file(path):
        return False
    return pure.suffix.lower() in {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rb", ".java"}


def _matches_likely_path(path: str, likely_files: set[str]) -> bool:
    pure = PurePosixPath(path)
    for candidate in likely_files:
        if path == candidate:
            return True
        candidate_pure = PurePosixPath(candidate)
        if pure.name == candidate_pure.name:
            return True
    return False


def _has_manual_only_validation(engineering: EngineeringResult | None) -> bool:
    if engineering is None or not engineering.test_actions:
        return True
    lowered = [item.lower() for item in engineering.test_actions]
    if any("run " in item or "pytest" in item or "unit test" in item or "test suite" in item for item in lowered):
        return False
    return any("manual" in item for item in lowered)


def _build_summary(
    *,
    touched_files: list[str],
    code_files: list[str],
    test_files: list[str],
    out_of_plan_files: list[str],
    code_changes_without_tests: bool,
    manual_validation_only: bool,
    risky_change_size: bool,
) -> str:
    parts = [f"touched={len(touched_files)}", f"code={len(code_files)}", f"tests={len(test_files)}"]
    if out_of_plan_files:
        parts.append(f"out_of_plan={len(out_of_plan_files)}")
    if code_changes_without_tests:
        parts.append("missing_test_coverage=true")
    if manual_validation_only:
        parts.append("manual_validation_only=true")
    if risky_change_size:
        parts.append("risky_change_size=true")
    return " ".join(parts)
