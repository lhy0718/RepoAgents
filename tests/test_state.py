from __future__ import annotations

import json
from pathlib import Path

from reporepublic.models import CURRENT_RUN_STATE_VERSION, RunLifecycle, RunRecord
from reporepublic.orchestrator import RunStateStore


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
