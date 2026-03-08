from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "webhook_receiver.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("reporepublic_webhook_receiver", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_signature_roundtrip() -> None:
    module = _load_module()
    body = b'{"action":"opened"}'
    signature = module.compute_signature("demo-secret", body)

    assert signature.startswith("sha256=")
    assert module.signature_matches("demo-secret", body, signature) is True
    assert module.signature_matches("demo-secret", body, "sha256=deadbeef") is False
    assert module.signature_matches("demo-secret", body, None) is False


def test_resolve_webhook_secret_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.setenv("RR_SECRET", "super-secret")

    assert module.resolve_webhook_secret(None, "RR_SECRET") == "super-secret"


def test_resolve_webhook_secret_raises_on_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.delenv("RR_SECRET", raising=False)

    with pytest.raises(SystemExit):
        module.resolve_webhook_secret(None, "RR_SECRET")
