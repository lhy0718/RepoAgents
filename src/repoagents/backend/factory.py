from __future__ import annotations

from repoagents.backend.base import BackendRunner
from repoagents.backend.codex import CodexBackend
from repoagents.config import LoadedConfig


def build_backend(loaded: LoadedConfig) -> BackendRunner:
    return CodexBackend(
        command=loaded.data.codex.command,
        model=loaded.data.codex.model,
        approval_policy=loaded.data.codex.approval_policy,
        default_sandbox=loaded.data.codex.sandbox,
        extra_args=loaded.data.codex.extra_args,
    )
