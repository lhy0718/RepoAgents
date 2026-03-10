from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["FakeBackend", "install_fake_codex_shim"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    module = import_module("repoagents.testing.fake_codex")
    return getattr(module, name)
