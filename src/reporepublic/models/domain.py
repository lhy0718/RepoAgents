from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


CURRENT_RUN_STATE_VERSION = 1
LEGACY_RUN_STATE_VERSION = 0


class RoleName(StrEnum):
    TRIAGE = "triage"
    PLANNER = "planner"
    ENGINEER = "engineer"
    QA = "qa"
    REVIEWER = "reviewer"


class IssueType(StrEnum):
    BUG = "bug"
    FEATURE = "feature"
    DOCS = "docs"
    CHORE = "chore"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"


class QAStatus(StrEnum):
    PASS = "pass"
    NEEDS_FOLLOW_UP = "needs_follow_up"


class PublicationMode(StrEnum):
    COMMENT_ONLY = "comment_only"
    DRAFT_PR = "draft_pr"
    HUMAN_APPROVAL = "human_approval"


class RunLifecycle(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RETRY_PENDING = "retry_pending"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class IssueComment(BaseModel):
    author: str = "unknown"
    body: str
    created_at: datetime | None = None


class IssueRef(BaseModel):
    id: int
    number: int | None = None
    title: str
    body: str = ""
    labels: list[str] = Field(default_factory=list)
    comments: list[IssueComment] = Field(default_factory=list)
    url: str | None = None
    updated_at: datetime | None = None

    def fingerprint(self) -> str:
        payload = {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "labels": sorted(self.labels),
            "comments": [comment.model_dump(mode="json") for comment in self.comments],
        }
        return sha256(str(payload).encode("utf-8")).hexdigest()[:16]

    def comments_excerpt(self, limit: int = 3) -> str:
        selected = self.comments[-limit:]
        if not selected:
            return "No recent comments."
        lines = []
        for comment in selected:
            lines.append(f"- {comment.author}: {comment.body.strip()}")
        return "\n".join(lines)


class TriageResult(BaseModel):
    issue_type: IssueType
    priority: Priority
    duplicate_candidates: list[str] = Field(default_factory=list)
    summary: str


class PlanResult(BaseModel):
    plan_steps: list[str] = Field(default_factory=list)
    likely_files: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    summary: str


class EngineeringResult(BaseModel):
    changed_files: list[str] = Field(default_factory=list)
    patch_summary: str
    test_actions: list[str] = Field(default_factory=list)
    summary: str


class QAResult(BaseModel):
    status: QAStatus
    recommended_commands: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    summary: str


class ReviewResult(BaseModel):
    decision: ReviewDecision
    risk_level: RiskLevel
    review_notes: list[str] = Field(default_factory=list)
    summary: str


class DiffReport(BaseModel):
    changed_files: list[str] = Field(default_factory=list)
    added_files: list[str] = Field(default_factory=list)
    removed_files: list[str] = Field(default_factory=list)
    total_added_lines: int = 0
    total_removed_lines: int = 0
    unified_diff: str = ""
    summary: str = ""


class ReviewSignals(BaseModel):
    touched_files: list[str] = Field(default_factory=list)
    code_files: list[str] = Field(default_factory=list)
    test_files: list[str] = Field(default_factory=list)
    out_of_plan_files: list[str] = Field(default_factory=list)
    code_changes_without_tests: bool = False
    manual_validation_only: bool = False
    risky_change_size: bool = False
    summary: str = ""


class ExternalActionResult(BaseModel):
    action: str
    executed: bool
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    run_id: str
    issue_id: int
    issue_title: str
    fingerprint: str
    status: RunLifecycle
    current_role: str | None = None
    attempts: int = 0
    dry_run: bool = False
    workspace_path: str | None = None
    backend_mode: str = "codex"
    started_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    last_error: str | None = None
    next_retry_at: datetime | None = None
    summary: str | None = None
    role_artifacts: dict[str, str] = Field(default_factory=dict)
    external_actions: list[ExternalActionResult] = Field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = utc_now()


class RunStateFile(BaseModel):
    version: int = CURRENT_RUN_STATE_VERSION
    runs: dict[str, RunRecord] = Field(default_factory=dict)
