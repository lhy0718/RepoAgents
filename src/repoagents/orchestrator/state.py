from __future__ import annotations

from datetime import datetime
from pathlib import Path

from repoagents.models import (
    CURRENT_RUN_STATE_VERSION,
    CURRENT_WORKER_STATE_VERSION,
    RunLifecycle,
    RunRecord,
    RunStateFile,
    WorkerLifecycle,
    WorkerMode,
    WorkerRecord,
    WorkerStateFile,
)
from repoagents.models.domain import utc_now
from repoagents.utils.files import ensure_dir, load_json_file, write_json_file


class RunStateMigrationError(RuntimeError):
    """Raised when RepoAgents cannot migrate the persisted run state file."""


class WorkerStateMigrationError(RuntimeError):
    """Raised when RepoAgents cannot migrate the persisted worker state file."""


class RunStateStore:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        ensure_dir(self.state_file.parent)
        self._state = self._load()

    def _load(self) -> RunStateFile:
        payload = load_json_file(
            self.state_file,
            default={"version": CURRENT_RUN_STATE_VERSION, "runs": {}},
        )
        migrated = migrate_run_state_payload(payload)
        state = RunStateFile.model_validate(migrated)
        if migrated != payload:
            self._state = state
            self.save()
        return state

    def save(self) -> None:
        write_json_file(self.state_file, self._state.model_dump(mode="json"))

    def all(self) -> list[RunRecord]:
        return sorted(
            self._state.runs.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )

    def get(self, issue_id: int) -> RunRecord | None:
        return self._state.runs.get(str(issue_id))

    def upsert(self, record: RunRecord) -> None:
        record.touch()
        self._state.runs[str(record.issue_id)] = record
        self.save()

    def force_retry(self, issue_id: int, reason: str) -> RunRecord | None:
        record = self.get(issue_id)
        if record is None:
            return None
        record.status = RunLifecycle.RETRY_PENDING
        record.next_retry_at = utc_now()
        record.finished_at = None
        record.current_role = None
        record.last_error = reason
        self.upsert(record)
        return record

    def recover_in_progress_runs(self) -> list[RunRecord]:
        recovered: list[RunRecord] = []
        for record in self._state.runs.values():
            if record.status == RunLifecycle.IN_PROGRESS:
                record.status = RunLifecycle.RETRY_PENDING
                record.last_error = "Recovered interrupted in-progress run after process restart."
                record.next_retry_at = utc_now()
                record.touch()
                recovered.append(record)
        if recovered:
            self.save()
        return recovered


class WorkerStateStore:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        ensure_dir(self.state_file.parent)
        self._state = self._load()

    def _load(self) -> WorkerStateFile:
        payload = load_json_file(
            self.state_file,
            default={"version": CURRENT_WORKER_STATE_VERSION, "worker": None},
        )
        migrated = migrate_worker_state_payload(payload)
        state = WorkerStateFile.model_validate(migrated)
        if migrated != payload:
            self._state = state
            self.save()
        return state

    def refresh(self) -> WorkerStateFile:
        self._state = self._load()
        return self._state

    def save(self) -> None:
        write_json_file(self.state_file, self._state.model_dump(mode="json"))

    def get(self) -> WorkerRecord | None:
        self.refresh()
        return self._state.worker

    def holds_lease(self, worker_id: str) -> bool:
        record = self.get()
        return bool(
            record
            and record.worker_id == worker_id
            and record.status != WorkerLifecycle.STOPPED
        )

    def start(
        self,
        *,
        worker_id: str,
        pid: int,
        mode: WorkerMode,
        poll_interval_seconds: int,
    ) -> WorkerRecord:
        record = WorkerRecord(
            worker_id=worker_id,
            pid=pid,
            mode=mode,
            status=WorkerLifecycle.STARTING,
            poll_interval_seconds=poll_interval_seconds,
        )
        self._state.worker = record
        self.save()
        return record

    def heartbeat(
        self,
        worker_id: str,
        *,
        status: WorkerLifecycle | None = None,
    ) -> WorkerRecord | None:
        record = self.get()
        if record is None or record.worker_id != worker_id:
            return None
        if status is not None:
            record.status = status
        record.touch()
        self._state.worker = record
        self.save()
        return record

    def begin_poll(self, worker_id: str) -> WorkerRecord | None:
        record = self.get()
        if record is None or record.worker_id != worker_id:
            return None
        record.status = WorkerLifecycle.POLLING
        record.last_poll_started_at = utc_now()
        record.touch()
        self._state.worker = record
        self.save()
        return record

    def complete_poll(self, worker_id: str, *, run_count: int) -> WorkerRecord | None:
        record = self.get()
        if record is None or record.worker_id != worker_id:
            return None
        record.status = WorkerLifecycle.IDLE
        record.last_poll_completed_at = utc_now()
        record.last_poll_run_count = run_count
        record.last_error = None
        record.touch()
        self._state.worker = record
        self.save()
        return record

    def fail_poll(self, worker_id: str, *, error: str) -> WorkerRecord | None:
        record = self.get()
        if record is None or record.worker_id != worker_id:
            return None
        record.status = WorkerLifecycle.IDLE
        record.last_poll_completed_at = utc_now()
        record.last_poll_run_count = 0
        record.last_error = error
        record.touch()
        self._state.worker = record
        self.save()
        return record

    def request_stop(self, *, reason: str) -> WorkerRecord | None:
        record = self.get()
        if record is None:
            return None
        record.stop_requested_at = utc_now()
        record.stop_reason = reason
        record.touch()
        self._state.worker = record
        self.save()
        return record

    def stop_requested(self, worker_id: str) -> bool:
        record = self.get()
        return bool(record and record.worker_id == worker_id and record.stop_requested_at is not None)

    def mark_stopped(self, worker_id: str, *, reason: str | None = None) -> WorkerRecord | None:
        record = self.get()
        if record is None or record.worker_id != worker_id:
            return None
        record.status = WorkerLifecycle.STOPPED
        record.stopped_at = utc_now()
        if reason is not None:
            record.stop_reason = reason
        record.touch()
        self._state.worker = record
        self.save()
        return record


def migrate_run_state_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise RunStateMigrationError("Run state payload must be a JSON object.")

    working = dict(payload)
    version = working.get("version", 0)
    if not isinstance(version, int):
        raise RunStateMigrationError("Run state version must be an integer.")
    if version > CURRENT_RUN_STATE_VERSION:
        raise RunStateMigrationError(
            f"Unsupported run state version {version}; current version is {CURRENT_RUN_STATE_VERSION}."
        )

    while version < CURRENT_RUN_STATE_VERSION:
        if version == 0:
            working = _migrate_v0_to_v1(working)
            version = working["version"]
            continue
        if version == 1:
            working = _migrate_v1_to_v2(working)
            version = working["version"]
            continue
        raise RunStateMigrationError(f"No migration path is defined for run state version {version}.")
    return working


def _migrate_v0_to_v1(payload: dict) -> dict:
    return {
        "version": 1,
        "runs": payload.get("runs", {}),
    }


def _migrate_v1_to_v2(payload: dict) -> dict:
    migrated_runs: dict[str, object] = {}
    raw_runs = payload.get("runs", {})
    if isinstance(raw_runs, dict):
        for issue_id, raw_record in raw_runs.items():
            if isinstance(raw_record, dict) and "approval_request" not in raw_record:
                migrated_runs[str(issue_id)] = {
                    **raw_record,
                    "approval_request": None,
                }
            else:
                migrated_runs[str(issue_id)] = raw_record
    return {
        "version": 2,
        "runs": migrated_runs,
    }


def migrate_worker_state_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise WorkerStateMigrationError("Worker state payload must be a JSON object.")

    working = dict(payload)
    version = working.get("version", 0)
    if not isinstance(version, int):
        raise WorkerStateMigrationError("Worker state version must be an integer.")
    if version > CURRENT_WORKER_STATE_VERSION:
        raise WorkerStateMigrationError(
            f"Unsupported worker state version {version}; current version is {CURRENT_WORKER_STATE_VERSION}."
        )

    while version < CURRENT_WORKER_STATE_VERSION:
        if version == 0:
            working = _migrate_worker_v0_to_v1(working)
            version = working["version"]
            continue
        raise WorkerStateMigrationError(
            f"No migration path is defined for worker state version {version}."
        )
    return working


def _migrate_worker_v0_to_v1(payload: dict) -> dict:
    return {
        "version": 1,
        "worker": payload.get("worker"),
    }


def load_worker_runtime_snapshot(
    state_file: Path,
    *,
    expected_poll_interval_seconds: int,
    now: datetime | None = None,
) -> dict[str, object]:
    store = WorkerStateStore(state_file)
    return serialize_worker_runtime_snapshot(
        store.get(),
        expected_poll_interval_seconds=expected_poll_interval_seconds,
        now=now,
    )


def serialize_worker_runtime_snapshot(
    record: WorkerRecord | None,
    *,
    expected_poll_interval_seconds: int,
    now: datetime | None = None,
) -> dict[str, object]:
    current = now or utc_now()
    heartbeat_timeout_seconds = worker_heartbeat_timeout_seconds(
        record.poll_interval_seconds if record is not None else expected_poll_interval_seconds
    )
    if record is None:
        return {
            "status": "not_running",
            "raw_status": None,
            "worker_id": None,
            "pid": None,
            "mode": None,
            "healthy": False,
            "stale": False,
            "heartbeat_timeout_seconds": heartbeat_timeout_seconds,
            "started_at": None,
            "updated_at": None,
            "last_heartbeat_at": None,
            "heartbeat_age_seconds": None,
            "heartbeat_age_human": "n/a",
            "last_poll_started_at": None,
            "last_poll_completed_at": None,
            "last_poll_run_count": 0,
            "last_poll_age_seconds": None,
            "last_poll_age_human": "n/a",
            "stop_requested": False,
            "stop_requested_at": None,
            "stop_reason": None,
            "stopped_at": None,
            "last_error": None,
            "poll_interval_seconds": expected_poll_interval_seconds,
        }

    heartbeat_age_seconds = _age_seconds(current, record.last_heartbeat_at)
    stale = (
        record.status != WorkerLifecycle.STOPPED
        and heartbeat_age_seconds is not None
        and heartbeat_age_seconds > heartbeat_timeout_seconds
    )
    derived_status = record.status.value
    if stale:
        derived_status = "stale"
    elif record.stop_requested_at is not None and record.status != WorkerLifecycle.STOPPED:
        derived_status = "stop_requested"

    poll_reference = record.last_poll_completed_at or record.last_poll_started_at
    poll_age_seconds = _age_seconds(current, poll_reference)
    return {
        "status": derived_status,
        "raw_status": record.status.value,
        "worker_id": record.worker_id,
        "pid": record.pid,
        "mode": record.mode.value,
        "healthy": record.status != WorkerLifecycle.STOPPED and not stale,
        "stale": stale,
        "heartbeat_timeout_seconds": heartbeat_timeout_seconds,
        "started_at": record.started_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "last_heartbeat_at": record.last_heartbeat_at.isoformat(),
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "heartbeat_age_human": _format_age_seconds(heartbeat_age_seconds),
        "last_poll_started_at": record.last_poll_started_at.isoformat() if record.last_poll_started_at else None,
        "last_poll_completed_at": (
            record.last_poll_completed_at.isoformat() if record.last_poll_completed_at else None
        ),
        "last_poll_run_count": record.last_poll_run_count,
        "last_poll_age_seconds": poll_age_seconds,
        "last_poll_age_human": _format_age_seconds(poll_age_seconds),
        "stop_requested": record.stop_requested_at is not None and record.status != WorkerLifecycle.STOPPED,
        "stop_requested_at": record.stop_requested_at.isoformat() if record.stop_requested_at else None,
        "stop_reason": record.stop_reason,
        "stopped_at": record.stopped_at.isoformat() if record.stopped_at else None,
        "last_error": record.last_error,
        "poll_interval_seconds": record.poll_interval_seconds,
    }


def worker_heartbeat_timeout_seconds(poll_interval_seconds: int) -> int:
    return max(30, poll_interval_seconds * 2 + 5)


def _age_seconds(now: datetime, timestamp: datetime | None) -> int | None:
    if timestamp is None:
        return None
    return max(int((now - timestamp).total_seconds()), 0)


def _format_age_seconds(value: int | None) -> str:
    if value is None:
        return "n/a"
    days, remainder = divmod(value, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts[:2])
