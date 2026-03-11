from __future__ import annotations

import json
import os
from pathlib import Path

from repoagents.models import (
    ApprovalActionProposal,
    ApprovalRequest,
    ApprovalStatus,
    CURRENT_RUN_STATE_VERSION,
    CURRENT_WORKER_STATE_VERSION,
    RunLifecycle,
    RunRecord,
    WorkerMode,
)
from repoagents.orchestrator import RunStateStore, WorkerStateStore, load_worker_runtime_snapshot


def test_run_state_recovery_marks_in_progress_as_retry_pending(tmp_path: Path) -> None:
    store = RunStateStore(tmp_path / "runs.json")
    record = RunRecord(
        run_id="run-1",
        issue_id=1,
        issue_title="Broken issue",
        fingerprint="abc123",
        status=RunLifecycle.IN_PROGRESS,
    )
    store.upsert(record)

    reloaded = RunStateStore(tmp_path / "runs.json")
    recovered = reloaded.recover_in_progress_runs()
    assert len(recovered) == 1
    assert recovered[0].status == RunLifecycle.RETRY_PENDING


def test_run_state_file_writes_schema_version(tmp_path: Path) -> None:
    store = RunStateStore(tmp_path / "runs.json")
    store.upsert(
        RunRecord(
            run_id="run-1",
            issue_id=1,
            issue_title="Versioned issue",
            fingerprint="versioned-1",
            status=RunLifecycle.COMPLETED,
        )
    )

    payload = json.loads((tmp_path / "runs.json").read_text(encoding="utf-8"))
    assert payload["version"] == CURRENT_RUN_STATE_VERSION
    assert "1" in payload["runs"]


def test_run_state_store_migrates_legacy_payload_without_version(tmp_path: Path) -> None:
    legacy_payload = {
        "runs": {
            "7": {
                "run_id": "run-7",
                "issue_id": 7,
                "issue_title": "Legacy issue",
                "fingerprint": "legacy-7",
                "status": "completed",
            }
        }
    }
    state_file = tmp_path / "runs.json"
    state_file.write_text(json.dumps(legacy_payload), encoding="utf-8")

    store = RunStateStore(state_file)

    record = store.get(7)
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert record is not None
    assert record.issue_title == "Legacy issue"
    assert payload["version"] == CURRENT_RUN_STATE_VERSION


def test_run_state_store_migrates_explicit_version_zero_payload(tmp_path: Path) -> None:
    legacy_payload = {
        "version": 0,
        "runs": {
            "9": {
                "run_id": "run-9",
                "issue_id": 9,
                "issue_title": "Explicit legacy issue",
                "fingerprint": "legacy-9",
                "status": "retry_pending",
            }
        },
    }
    state_file = tmp_path / "runs.json"
    state_file.write_text(json.dumps(legacy_payload), encoding="utf-8")

    store = RunStateStore(state_file)

    record = store.get(9)
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert record is not None
    assert record.status == RunLifecycle.RETRY_PENDING
    assert payload["version"] == CURRENT_RUN_STATE_VERSION


def test_run_state_store_migrates_v1_payload_to_include_approval_request(tmp_path: Path) -> None:
    legacy_payload = {
        "version": 1,
        "runs": {
            "3": {
                "run_id": "run-3",
                "issue_id": 3,
                "issue_title": "Legacy approval-less issue",
                "fingerprint": "legacy-3",
                "status": "completed",
            }
        },
    }
    state_file = tmp_path / "runs.json"
    state_file.write_text(json.dumps(legacy_payload), encoding="utf-8")

    store = RunStateStore(state_file)

    record = store.get(3)
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert record is not None
    assert record.approval_request is None
    assert payload["version"] == CURRENT_RUN_STATE_VERSION
    assert payload["runs"]["3"]["approval_request"] is None


def test_worker_state_store_writes_schema_version_and_runtime_snapshot(tmp_path: Path) -> None:
    store = WorkerStateStore(tmp_path / "worker.json")
    record = store.start(
        worker_id="worker-1",
        pid=os.getpid(),
        mode=WorkerMode.SERVICE,
        poll_interval_seconds=60,
    )
    store.complete_poll(record.worker_id, run_count=2)

    payload = json.loads((tmp_path / "worker.json").read_text(encoding="utf-8"))
    snapshot = load_worker_runtime_snapshot(
        tmp_path / "worker.json",
        expected_poll_interval_seconds=60,
    )
    assert payload["version"] == CURRENT_WORKER_STATE_VERSION
    assert payload["worker"]["worker_id"] == "worker-1"
    assert snapshot["status"] == "idle"
    assert snapshot["pid"] == os.getpid()
    assert snapshot["last_poll_run_count"] == 2


def test_worker_state_store_tracks_active_lease_holder(tmp_path: Path) -> None:
    store = WorkerStateStore(tmp_path / "worker.json")
    store.start(
        worker_id="worker-1",
        pid=os.getpid(),
        mode=WorkerMode.SERVICE,
        poll_interval_seconds=60,
    )

    assert store.holds_lease("worker-1") is True

    store.start(
        worker_id="worker-2",
        pid=os.getpid(),
        mode=WorkerMode.SERVICE,
        poll_interval_seconds=60,
    )

    assert store.holds_lease("worker-1") is False
    assert store.holds_lease("worker-2") is True

    store.mark_stopped("worker-2")

    assert store.holds_lease("worker-2") is False


def test_run_state_store_persists_approval_request_payload(tmp_path: Path) -> None:
    store = RunStateStore(tmp_path / "runs.json")
    store.upsert(
        RunRecord(
            run_id="run-11",
            issue_id=11,
            issue_title="Approval pending issue",
            fingerprint="approval-11",
            status=RunLifecycle.COMPLETED,
            approval_request=ApprovalRequest(
                status=ApprovalStatus.PENDING,
                summary="Maintainer approval required before publish.",
                policy_summary="Human approval remains required before publishing changes.",
                review_summary="Reviewer approved with low risk.",
                actions=[
                    ApprovalActionProposal(
                        action="post_comment",
                        summary="Post the generated issue comment.",
                    )
                ],
            ),
        )
    )

    payload = json.loads((tmp_path / "runs.json").read_text(encoding="utf-8"))
    assert payload["version"] == CURRENT_RUN_STATE_VERSION
    assert payload["runs"]["11"]["approval_request"]["status"] == "pending"
