from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class BackendExecutionError(RuntimeError):
    """Raised when a backend invocation fails."""


@dataclass(slots=True)
class BackendRunResult:
    payload: BaseModel
    raw_output: str


@dataclass(slots=True)
class BackendInvocation:
    role_name: str
    prompt: str
    output_model: type[BaseModel]
    cwd: Path
    timeout_seconds: int
    allow_write: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class BackendRunner(ABC):
    @abstractmethod
    async def run_structured(self, invocation: BackendInvocation) -> BackendRunResult:
        raise NotImplementedError
