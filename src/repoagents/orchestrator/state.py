from __future__ import annotations

from pathlib import Path

from repoagents.models import CURRENT_RUN_STATE_VERSION, RunLifecycle, RunRecord, RunStateFile
from repoagents.models.domain import utc_now
from repoagents.utils.files import ensure_dir, load_json_file, write_json_file


class RunStateMigrationError(RuntimeError):
    """Raised when RepoAgents cannot migrate the persisted run state file."""


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
        raise RunStateMigrationError(f"No migration path is defined for run state version {version}.")
    return working


def _migrate_v0_to_v1(payload: dict) -> dict:
    return {
        "version": 1,
        "runs": payload.get("runs", {}),
    }
