from __future__ import annotations

from reporepublic.backend.base import BackendRunner
from reporepublic.backend.codex import CodexBackend
from reporepublic.backend.mock import MockBackend
from reporepublic.config import LoadedConfig
from reporepublic.config.models import LLMMode


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
