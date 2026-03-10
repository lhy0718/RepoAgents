from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class GitHubTokenResolution:
    token: str | None
    source: str
    token_env: str
    gh_path: str | None
    gh_authenticated: bool
    error: str | None = None

    @property
    def token_present(self) -> bool:
        return bool(self.token)


def resolve_github_token(token_env: str) -> GitHubTokenResolution:
    token = os.getenv(token_env)
    gh_path = shutil.which("gh")
    if token:
        return GitHubTokenResolution(
            token=token,
            source="token_env",
            token_env=token_env,
            gh_path=gh_path,
            gh_authenticated=False,
        )

    if not gh_path:
        return GitHubTokenResolution(
            token=None,
            source="missing",
            token_env=token_env,
            gh_path=None,
            gh_authenticated=False,
        )

    token_result = _run_gh_command(["gh", "auth", "token", "--hostname", "github.com"])
    resolved_token = token_result.stdout.strip() if token_result and token_result.returncode == 0 else ""
    if resolved_token:
        return GitHubTokenResolution(
            token=resolved_token,
            source="gh_cli",
            token_env=token_env,
            gh_path=gh_path,
            gh_authenticated=True,
        )

    status_result = _run_gh_command(["gh", "auth", "status", "--hostname", "github.com"])
    gh_authenticated = bool(status_result and status_result.returncode == 0)
    error = None
    if token_result:
        error = (token_result.stderr or token_result.stdout).strip() or None
    elif status_result:
        error = (status_result.stderr or status_result.stdout).strip() or None

    return GitHubTokenResolution(
        token=None,
        source="missing",
        token_env=token_env,
        gh_path=gh_path,
        gh_authenticated=gh_authenticated,
        error=error,
    )


def _run_gh_command(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
