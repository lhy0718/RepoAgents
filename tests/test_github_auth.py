from __future__ import annotations

from repoagents.github_auth import resolve_github_token


def test_resolve_github_token_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    called: list[list[str]] = []

    monkeypatch.setattr("repoagents.github_auth.shutil.which", lambda command: "/opt/test/gh")
    monkeypatch.setattr(
        "repoagents.github_auth._run_gh_command",
        lambda command: called.append(command) or None,
    )

    resolution = resolve_github_token("GITHUB_TOKEN")

    assert resolution.token == "env-token"
    assert resolution.source == "token_env"
    assert called == []


def test_resolve_github_token_uses_gh_auth_token_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("repoagents.github_auth.shutil.which", lambda command: "/opt/test/gh")

    class Completed:
        returncode = 0
        stdout = "gh-token\n"
        stderr = ""

    monkeypatch.setattr("repoagents.github_auth._run_gh_command", lambda command: Completed())

    resolution = resolve_github_token("GITHUB_TOKEN")

    assert resolution.token == "gh-token"
    assert resolution.source == "gh_cli"
    assert resolution.gh_authenticated is True


def test_resolve_github_token_reports_missing_when_gh_is_not_authenticated(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("repoagents.github_auth.shutil.which", lambda command: "/opt/test/gh")

    class Failed:
        returncode = 1
        stdout = ""
        stderr = "not logged in"

    monkeypatch.setattr("repoagents.github_auth._run_gh_command", lambda command: Failed())

    resolution = resolve_github_token("GITHUB_TOKEN")

    assert resolution.token is None
    assert resolution.source == "missing"
    assert resolution.gh_authenticated is False
