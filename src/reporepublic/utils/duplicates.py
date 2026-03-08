from __future__ import annotations

import re
from dataclasses import dataclass

from reporepublic.models import IssueRef


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "when",
    "with",
}


@dataclass(slots=True)
class DuplicateCandidate:
    issue_id: int
    title: str
    score: float
    overlap_terms: list[str]
    labels: list[str]

    def to_metadata(self) -> dict[str, object]:
        return {
            "issue_id": self.issue_id,
            "title": self.title,
            "score": round(self.score, 3),
            "overlap_terms": self.overlap_terms,
            "labels": self.labels,
        }


def rank_duplicate_candidates(
    issue: IssueRef,
    open_issues: list[IssueRef],
    *,
    limit: int = 5,
    min_score: float = 0.34,
) -> list[DuplicateCandidate]:
    current_title_tokens = _tokenize(issue.title)
    current_text_tokens = _tokenize(f"{issue.title}\n{issue.body}")
    current_labels = {label.lower() for label in issue.labels}
    current_normalized_title = _normalize_title(issue.title)

    ranked: list[DuplicateCandidate] = []
    for other in open_issues:
        if other.id == issue.id:
            continue
        other_title_tokens = _tokenize(other.title)
        other_text_tokens = _tokenize(f"{other.title}\n{other.body}")
        other_labels = {label.lower() for label in other.labels}
        title_similarity = _jaccard(current_title_tokens, other_title_tokens)
        text_similarity = _jaccard(current_text_tokens, other_text_tokens)
        label_similarity = _jaccard(current_labels, other_labels)
        normalized_other_title = _normalize_title(other.title)

        score = (title_similarity * 0.55) + (text_similarity * 0.3) + (label_similarity * 0.15)
        if current_normalized_title and current_normalized_title == normalized_other_title:
            score = max(score, 0.98)
        elif current_normalized_title and (
            current_normalized_title in normalized_other_title
            or normalized_other_title in current_normalized_title
        ):
            score = min(1.0, score + 0.15)

        if score < min_score:
            continue

        overlap_terms = sorted(current_text_tokens & other_text_tokens)[:6]
        ranked.append(
            DuplicateCandidate(
                issue_id=other.id,
                title=other.title,
                score=score,
                overlap_terms=overlap_terms,
                labels=other.labels,
            )
        )

    ranked.sort(key=lambda candidate: (-candidate.score, candidate.issue_id))
    return ranked[:limit]


def render_duplicate_candidates_context(candidates: list[DuplicateCandidate]) -> str:
    if not candidates:
        return "- No strong duplicate candidates found among current open issues."
    lines: list[str] = []
    for candidate in candidates:
        overlap = ", ".join(candidate.overlap_terms) if candidate.overlap_terms else "weak lexical overlap"
        labels = ", ".join(candidate.labels) if candidate.labels else "none"
        lines.append(
            f"- #{candidate.issue_id} score={candidate.score:.2f} title={candidate.title} "
            f"labels={labels} overlap={overlap}"
        )
    return "\n".join(lines)


def _tokenize(text: str) -> set[str]:
    tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", text.lower())
        if len(token) >= 2 and token not in STOPWORDS and not token.isdigit()
    }
    return tokens


def _normalize_title(title: str) -> str:
    return " ".join(sorted(_tokenize(title)))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)
