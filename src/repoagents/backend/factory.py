from __future__ import annotations

from repoagents.backend.base import BackendRunner
from repoagents.backend.codex import CodexBackend
from repoagents.backend.mock import MockBackend
from repoagents.config import LoadedConfig
from repoagents.config.models import LLMMode


def build_backend(loaded: LoadedConfig) -> BackendRunner:
    if loaded.data.llm.mode == LLMMode.MOCK:
        return MockBackend()
    return CodexBackend(
        command=loaded.data.codex.command,
        model=loaded.data.codex.model,
        approval_policy=loaded.data.codex.approval_policy,
        default_sandbox=loaded.data.codex.sandbox,
        extra_args=loaded.data.codex.extra_args,
    )
