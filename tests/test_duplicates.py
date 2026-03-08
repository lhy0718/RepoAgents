from __future__ import annotations

from reporepublic.models import IssueRef
from reporepublic.utils.duplicates import rank_duplicate_candidates, render_duplicate_candidates_context


def test_rank_duplicate_candidates_finds_similar_open_issue() -> None:
    issue = IssueRef(
        id=1,
        title="Fix empty input crash",
        body="Calling parse_items on an empty string crashes instead of returning an empty list.",
        labels=["bug"],
    )
    open_issues = [
        issue,
        IssueRef(
            id=2,
            title="Fix crash when parser receives empty input",
            body="Parser should return an empty list for empty input.",
            labels=["bug"],
        ),
        IssueRef(
            id=3,
            title="Improve README quickstart",
            body="Document install and test steps.",
            labels=["docs"],
        ),
    ]

    candidates = rank_duplicate_candidates(issue, open_issues)

    assert len(candidates) == 1
    assert candidates[0].issue_id == 2
    assert candidates[0].score >= 0.6
    assert "empty" in candidates[0].overlap_terms


def test_render_duplicate_candidates_context_handles_empty_candidates() -> None:
    context = render_duplicate_candidates_context([])

    assert context == "- No strong duplicate candidates found among current open issues."


def test_render_duplicate_candidates_context_formats_scores_and_labels() -> None:
    issue = IssueRef(
        id=1,
        title="Fix empty input crash",
        body="Parser crash on empty input.",
        labels=["bug"],
    )
    open_issues = [
        issue,
        IssueRef(
            id=4,
            title="Fix empty input crash in parser",
            body="Still crashes with empty values.",
            labels=["bug"],
        ),
    ]

    context = render_duplicate_candidates_context(rank_duplicate_candidates(issue, open_issues))

    assert "#4" in context
    assert "score=" in context
    assert "labels=bug" in context
