from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from pydantic import BaseModel

from repoagents.backend.base import BackendExecutionError, BackendInvocation, BackendRunResult, BackendRunner
from repoagents.utils.files import write_json_file
from repoagents.utils.prompting import extract_json_object


class CodexBackend(BackendRunner):
    def __init__(
        self,
        command: str,
        model: str,
        approval_policy: str,
        default_sandbox: str,
        extra_args: list[str] | None = None,
    ) -> None:
        self.command = command
        self.model = model
        self.approval_policy = approval_policy
        self.default_sandbox = default_sandbox
        self.extra_args = extra_args or []

    def command_exists(self) -> bool:
        return shutil.which(self.command) is not None

    def build_command(
        self,
        invocation: BackendInvocation,
        schema_path: Path,
        output_path: Path,
    ) -> list[str]:
        sandbox = self.default_sandbox if invocation.allow_write else "read-only"
        return [
            self.command,
            "-a",
            self.approval_policy,
            "exec",
            "-m",
            self.model,
            "-s",
            sandbox,
            "--skip-git-repo-check",
            "--ephemeral",
            "--color",
            "never",
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            "-C",
            str(invocation.cwd),
            *self.extra_args,
            "-",
        ]

    async def run_structured(self, invocation: BackendInvocation) -> BackendRunResult:
        if not self.command_exists():
            raise BackendExecutionError(
                f"Configured Codex command '{self.command}' is not available on PATH."
            )

        with tempfile.TemporaryDirectory(prefix="repoagents-codex-") as temp_dir:
            temp_root = Path(temp_dir)
            schema_path = temp_root / "schema.json"
            output_path = temp_root / "last-message.json"
            write_json_file(schema_path, invocation.output_model.model_json_schema())
            command = self.build_command(invocation, schema_path, output_path)
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(invocation.cwd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(invocation.prompt.encode("utf-8")),
                    timeout=invocation.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.communicate()
                raise BackendExecutionError(
                    f"Codex timed out after {invocation.timeout_seconds}s for role={invocation.role_name}"
                ) from exc

            if process.returncode != 0:
                raise BackendExecutionError(
                    "Codex backend failed: "
                    f"role={invocation.role_name} exit={process.returncode} "
                    f"stderr={stderr.decode('utf-8', errors='ignore').strip()} "
                    f"stdout={stdout.decode('utf-8', errors='ignore').strip()}"
                )

            raw_output = output_path.read_text(encoding="utf-8")
            try:
                payload = extract_json_object(raw_output)
            except Exception as exc:  # noqa: BLE001
                raise BackendExecutionError(
                    f"Codex returned malformed JSON for role={invocation.role_name}: "
                    f"{raw_output[:500]}"
                ) from exc
            try:
                model = invocation.output_model.model_validate(payload)
            except Exception as exc:  # noqa: BLE001
                raise BackendExecutionError(
                    f"Codex returned invalid structured output for role={invocation.role_name}: "
                    f"{json.dumps(payload, default=str)}"
                ) from exc
            return BackendRunResult(payload=model, raw_output=raw_output)
