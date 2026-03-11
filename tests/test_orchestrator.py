from __future__ import annotations

import asyncio
import os
from pathlib import Path

from repoagents.config import load_config
from repoagents.models import (
    ApprovalStatus,
    ExternalActionResult,
    IssueRef,
    PublicationMode,
    ReviewDecision,
    ReviewResult,
    ReviewSignals,
    RiskLevel,
    RoleName,
    RunLifecycle,
    WorkerLifecycle,
    WorkerMode,
)
from repoagents.orchestrator import Orchestrator, WorkerStateStore, load_worker_runtime_snapshot
from repoagents.tracker.base import Tracker


class RecordingTracker(Tracker):
    def __init__(self, issue: IssueRef) -> None:
        self.branch_calls: list[tuple[int, str]] = []
        self.pr_calls: list[tuple[int, str]] = []
        self.comment_calls: list[tuple[int, str]] = []
        self.issue = issue

    async def list_open_issues(self) -> list[IssueRef]:
        return [self.issue]

    async def get_issue(self, issue_id: int) -> IssueRef:
        return self.issue

    async def post_comment(self, issue_id: int, body: str) -> ExternalActionResult:
        self.comment_calls.append((issue_id, body))
        return ExternalActionResult(action="post_comment", executed=True, reason="ok")

    async def create_branch(
        self,
        issue_id: int,
        name: str,
        workspace_path: Path,
        commit_message: str,
    ) -> ExternalActionResult:
        self.branch_calls.append((issue_id, name))
        return ExternalActionResult(
            action="create_branch",
            executed=True,
            reason="ok",
            payload={"branch_name": name, "base_branch": "main"},
        )

    async def open_pr(
        self,
        issue_id: int,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        draft: bool = True,
    ) -> ExternalActionResult:
        self.pr_calls.append((issue_id, head_branch))
        return ExternalActionResult(
            action="open_pr",
            executed=True,
            reason="ok",
            payload={"url": "https://github.example/demo/repo/pull/1"},
        )

    async def set_issue_label(self, issue_id: int, labels: list[str]) -> ExternalActionResult:
        return ExternalActionResult(action="set_issue_label", executed=True, reason="ok")


def test_orchestrator_scheduling_and_duplicate_prevention(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    loaded.data.agent.max_concurrent_runs = 1
    orchestrator = Orchestrator(loaded, dry_run=False)
    first_pass = asyncio.run(orchestrator.run_once())
    assert len(first_pass) == 2
    assert all(record.status.value == "completed" for record in first_pass)

    second_pass = asyncio.run(orchestrator.run_once())
    assert second_pass == []


def test_orchestrator_persists_run_state(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    orchestrator = Orchestrator(loaded, dry_run=False)
    records = asyncio.run(orchestrator.run_once())
    assert records
    state_file = demo_repo / ".ai-repoagents" / "state" / "runs.json"
    assert state_file.exists()
    payload = state_file.read_text(encoding="utf-8")
    assert '"status": "completed"' in payload


def test_orchestrator_opens_pr_when_allowed(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    loaded.data.safety.allow_open_pr = True
    loaded.data.safety.allow_write_comments = False
    loaded.data.merge_policy.mode = PublicationMode.DRAFT_PR

    orchestrator = Orchestrator(loaded, dry_run=False)
    fake_tracker = RecordingTracker(
        IssueRef(
            id=1,
            number=1,
            title="Fix empty input crash",
            body="Calling parse_items on an empty string should return an empty list.",
            labels=["bug"],
            comments=[],
        )
    )
    orchestrator.tracker = fake_tracker
    records = asyncio.run(orchestrator.run_once())
    assert len(records) == 1
    assert fake_tracker.branch_calls
    assert fake_tracker.pr_calls
    assert any(action.action == "create_branch" for action in records[0].external_actions)
    assert any(action.action == "open_pr" for action in records[0].external_actions)


def test_orchestrator_comment_only_mode_does_not_open_pr_for_low_risk_changes(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    loaded.data.safety.allow_open_pr = True
    loaded.data.safety.allow_write_comments = False
    loaded.data.merge_policy.mode = PublicationMode.COMMENT_ONLY

    orchestrator = Orchestrator(loaded, dry_run=False)
    tracker = RecordingTracker(
        IssueRef(
            id=2,
            number=2,
            title="Improve README quickstart",
            body="Document install and test steps for contributors.",
            labels=["docs"],
            comments=[],
        )
    )
    orchestrator.tracker = tracker

    records = asyncio.run(orchestrator.run_once())

    assert len(records) == 1
    assert tracker.branch_calls == []
    assert tracker.pr_calls == []
    assert not any(action.action == "open_pr" for action in records[0].external_actions)


def test_orchestrator_draft_pr_mode_opens_pr_for_low_risk_changes(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    loaded.data.safety.allow_open_pr = True
    loaded.data.safety.allow_write_comments = False
    loaded.data.merge_policy.mode = PublicationMode.DRAFT_PR

    orchestrator = Orchestrator(loaded, dry_run=False)
    tracker = RecordingTracker(
        IssueRef(
            id=2,
            number=2,
            title="Improve README quickstart",
            body="Document install and test steps for contributors.",
            labels=["docs"],
            comments=[],
        )
    )
    orchestrator.tracker = tracker

    records = asyncio.run(orchestrator.run_once())

    assert len(records) == 1
    assert tracker.branch_calls
    assert tracker.pr_calls
    assert any(action.action == "open_pr" for action in records[0].external_actions)


def test_orchestrator_overrides_reviewer_approve_when_repo_criteria_require_changes(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    orchestrator = Orchestrator(loaded, dry_run=False)

    overridden = orchestrator._apply_review_overrides(
        reviewer=ReviewResult(
            decision=ReviewDecision.APPROVE,
            risk_level=RiskLevel.LOW,
            review_notes=["Looks reasonable at a glance."],
            summary="Reviewer decision: approve with low risk.",
        ),
        review_signals=ReviewSignals(
            touched_files=["src/parser.py", "src/auth.py", "tests/test_parser.py"],
            code_files=["src/parser.py", "src/auth.py"],
            test_files=["tests/test_parser.py"],
            out_of_plan_files=["src/auth.py"],
            code_changes_without_tests=False,
            manual_validation_only=True,
            risky_change_size=False,
            summary="touched=3 code=2 tests=1 out_of_plan=1 manual_validation_only=true",
        ),
        policy_findings=[],
    )

    assert overridden.decision == ReviewDecision.REQUEST_CHANGES
    assert overridden.risk_level == RiskLevel.HIGH
    assert any("manual-only validation" in note for note in overridden.review_notes)


def test_orchestrator_runs_optional_qa_role_when_enabled(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    loaded.data.roles.enabled = [
        RoleName.TRIAGE,
        RoleName.PLANNER,
        RoleName.ENGINEER,
        RoleName.QA,
        RoleName.REVIEWER,
    ]

    orchestrator = Orchestrator(loaded, dry_run=False)
    records = asyncio.run(orchestrator.run_once())

    assert len(records) == 2
    assert any("qa" in record.role_artifacts for record in records)


def test_orchestrator_runs_single_issue_by_id(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    orchestrator = Orchestrator(loaded, dry_run=False)

    record = asyncio.run(orchestrator.run_issue_by_id(1))

    assert record is not None
    assert record.issue_id == 1
    assert record.status == RunLifecycle.COMPLETED
    assert orchestrator.state_store.get(1) is not None
    assert orchestrator.state_store.get(2) is None


def test_orchestrator_handles_github_webhook_payload(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    orchestrator = Orchestrator(loaded, dry_run=False)

    decision, record = asyncio.run(
        orchestrator.handle_github_webhook(
            event="issues",
            payload={
                "action": "opened",
                "issue": {"number": 1, "state": "open"},
            },
        )
    )

    assert decision.should_run is True
    assert decision.issue_id == 1
    assert record is not None
    assert record.issue_id == 1
    assert record.status == RunLifecycle.COMPLETED


def test_orchestrator_run_forever_tracks_worker_state(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    loaded.data.tracker.poll_interval_seconds = 5
    orchestrator = Orchestrator(loaded, dry_run=False, worker_mode=WorkerMode.FOREGROUND)

    async def fake_run_once():
        worker = WorkerStateStore(loaded.state_dir / "worker.json").get()
        assert worker is not None
        assert worker.pid == os.getpid()
        assert worker.status == WorkerLifecycle.POLLING
        WorkerStateStore(loaded.state_dir / "worker.json").request_stop(reason="Stop requested from test.")
        return []

    orchestrator.run_once = fake_run_once  # type: ignore[method-assign]

    asyncio.run(orchestrator.run_forever())

    snapshot = load_worker_runtime_snapshot(
        loaded.state_dir / "worker.json",
        expected_poll_interval_seconds=loaded.data.tracker.poll_interval_seconds,
    )
    assert snapshot["status"] == "stopped"
    assert snapshot["mode"] == "foreground"
    assert snapshot["pid"] == os.getpid()
    assert snapshot["last_poll_completed_at"] is not None


def test_orchestrator_requeues_issue_when_worker_lease_is_replaced_before_publish(
    demo_repo: Path,
) -> None:
    loaded = load_config(demo_repo)
    loaded.data.safety.allow_open_pr = True
    loaded.data.safety.allow_write_comments = True

    issue = IssueRef(
        id=1,
        number=1,
        title="Fix empty input crash",
        body="Calling parse_items on an empty string should return an empty list.",
        labels=["bug"],
        comments=[],
    )
    orchestrator = Orchestrator(loaded, dry_run=False, worker_mode=WorkerMode.SERVICE)
    tracker = RecordingTracker(issue)
    orchestrator.tracker = tracker
    orchestrator.worker_id = "worker-1"
    orchestrator.worker_state_store.start(
        worker_id="worker-1",
        pid=os.getpid(),
        mode=WorkerMode.SERVICE,
        poll_interval_seconds=60,
    )
    original_run_role = orchestrator._run_role

    async def fake_run_role(record, role, context):
        result = await original_run_role(record, role, context)
        if role.name == "reviewer":
            orchestrator.worker_state_store.start(
                worker_id="worker-2",
                pid=os.getpid(),
                mode=WorkerMode.SERVICE,
                poll_interval_seconds=60,
            )
        return result

    orchestrator._run_role = fake_run_role  # type: ignore[method-assign]

    record = asyncio.run(orchestrator.run_issue_by_id(1, force=True))

    assert record is not None
    assert record.status == RunLifecycle.RETRY_PENDING
    assert record.next_retry_at is not None
    assert record.last_error is not None
    assert "lease lost" in record.last_error.lower()
    assert tracker.branch_calls == []
    assert tracker.pr_calls == []
    assert tracker.comment_calls == []


def test_orchestrator_stages_human_approval_request_without_external_writes(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    loaded.data.merge_policy.mode = PublicationMode.HUMAN_APPROVAL
    loaded.data.safety.allow_open_pr = True
    loaded.data.safety.allow_write_comments = True

    tracker = RecordingTracker(
        IssueRef(
            id=2,
            number=2,
            title="Improve README quickstart",
            body="Document install and test steps for contributors.",
            labels=["docs"],
            comments=[],
        )
    )
    orchestrator = Orchestrator(loaded, dry_run=False)
    orchestrator.tracker = tracker

    record = asyncio.run(orchestrator.run_issue_by_id(2, force=True))

    assert record is not None
    assert record.status == RunLifecycle.COMPLETED
    assert record.approval_request is not None
    assert record.approval_request.status == ApprovalStatus.PENDING
    assert [action.action for action in record.approval_request.actions] == [
        "post_comment",
        "create_branch",
        "open_pr",
    ]
    assert tracker.branch_calls == []
    assert tracker.pr_calls == []
    assert tracker.comment_calls == []
    assert "approval-request" in record.role_artifacts
