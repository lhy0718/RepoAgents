from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

import reporepublic.backend.codex as codex_module
from reporepublic.backend import BackendExecutionError, BackendInvocation, CodexBackend
from reporepublic.models import TriageResult


def test_codex_backend_command_builder() -> None:
    backend = CodexBackend(
        command="codex",
        model="gpt-5.4",
        approval_policy="never",
        default_sandbox="workspace-write",
    )
    invocation = BackendInvocation(
        role_name="triage",
        prompt="hello",
        output_model=TriageResult,
        cwd=Path("/tmp/workspace"),
        timeout_seconds=120,
        allow_write=False,
    )
    command = backend.build_command(
        invocation,
        Path("/tmp/schema.json"),
        Path("/tmp/output.json"),
    )
    assert command[:3] == ["codex", "-a", "never"]
    assert "exec" in command
    assert "--output-schema" in command
    assert "-C" in command
    assert "read-only" in command


def test_codex_backend_timeout_raises_execution_error(tmp_path: Path, monkeypatch) -> None:
    backend = CodexBackend(
        command="codex",
        model="gpt-5.4",
        approval_policy="never",
        default_sandbox="workspace-write",
    )
    monkeypatch.setattr(backend, "command_exists", lambda: True)

    class FakeProcess:
        returncode = 0

        async def communicate(self, input_data: bytes | None = None):
            del input_data
            return b"", b""

        def kill(self) -> None:
            return None

    async def fake_create_subprocess_exec(*args, **kwargs):
        del args, kwargs
        return FakeProcess()

    async def fake_wait_for(awaitable, timeout):
        del timeout
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(codex_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(codex_module.asyncio, "wait_for", fake_wait_for)

    invocation = BackendInvocation(
        role_name="triage",
        prompt="hello",
        output_model=TriageResult,
        cwd=tmp_path,
        timeout_seconds=1,
        allow_write=False,
    )

    with pytest.raises(BackendExecutionError) as excinfo:
        asyncio.run(backend.run_structured(invocation))

    assert "Codex timed out after 1s for role=triage" in str(excinfo.value)


def test_codex_backend_malformed_json_raises_execution_error(tmp_path: Path, monkeypatch) -> None:
    backend = CodexBackend(
        command="codex",
        model="gpt-5.4",
        approval_policy="never",
        default_sandbox="workspace-write",
    )
    monkeypatch.setattr(backend, "command_exists", lambda: True)

    class FakeProcess:
        def __init__(self, output_path: Path) -> None:
            self.returncode = 0
            self.output_path = output_path

        async def communicate(self, input_data: bytes | None = None):
            del input_data
            self.output_path.write_text("not-json", encoding="utf-8")
            return b"", b""

        def kill(self) -> None:
            return None

    async def fake_create_subprocess_exec(*args, **kwargs):
        del kwargs
        command = list(args)
        output_path = Path(command[command.index("-o") + 1])
        return FakeProcess(output_path)

    monkeypatch.setattr(codex_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    invocation = BackendInvocation(
        role_name="triage",
        prompt="hello",
        output_model=TriageResult,
        cwd=tmp_path,
        timeout_seconds=5,
        allow_write=False,
    )

    with pytest.raises(BackendExecutionError) as excinfo:
        asyncio.run(backend.run_structured(invocation))

    assert "Codex returned malformed JSON for role=triage" in str(excinfo.value)


@pytest.mark.skipif(
    os.getenv("CODEX_E2E") != "1" and os.getenv("REPOREPUBLIC_CODEX_E2E") != "1",
    reason="Set CODEX_E2E=1 or REPOREPUBLIC_CODEX_E2E=1 to run the live Codex smoke test.",
)
def test_codex_backend_live_smoke(tmp_path: Path) -> None:
    backend = CodexBackend(
        command=os.getenv("REPOREPUBLIC_CODEX_COMMAND", "codex"),
        model=os.getenv("REPOREPUBLIC_CODEX_MODEL", "gpt-5.4"),
        approval_policy="never",
        default_sandbox="workspace-write",
    )
    if not backend.command_exists():
        pytest.skip("Codex CLI is not installed on PATH.")

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# Codex Smoke Test\n", encoding="utf-8")

    prompt = """
Classify this synthetic issue for RepoRepublic.

Issue title: Improve README quickstart
Issue body: Add install and test commands for first-time contributors.

Return JSON only that matches the provided schema.
""".strip()

    invocation = BackendInvocation(
        role_name="triage",
        prompt=prompt,
        output_model=TriageResult,
        cwd=workspace,
        timeout_seconds=int(os.getenv("REPOREPUBLIC_CODEX_TIMEOUT", "180")),
        allow_write=False,
    )
    result = asyncio.run(backend.run_structured(invocation))
    assert isinstance(result.payload, TriageResult)
    assert result.payload.issue_type.value in {"bug", "feature", "docs", "chore"}
    assert result.payload.priority.value in {"low", "medium", "high"}
    assert result.payload.summary
    assert result.raw_output
