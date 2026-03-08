from __future__ import annotations

from reporepublic.config import LoadedConfig
from reporepublic.tracker.base import Tracker
from reporepublic.tracker.github import GitHubTracker
from reporepublic.tracker.local_file import LocalFileTracker
from reporepublic.tracker.local_markdown import LocalMarkdownTracker


def build_tracker(loaded: LoadedConfig, dry_run: bool = False) -> Tracker:
    config = loaded.data
    if config.tracker.kind == "github":
        fixtures_path = (
            loaded.resolve(config.tracker.fixtures_path) if config.tracker.fixtures_path else None
        )
        return GitHubTracker(
            repo=config.tracker.repo or "",
            api_url=config.tracker.api_url,
            token_env=config.tracker.token_env,
            repo_root=loaded.repo_root,
            mode=config.tracker.mode,
            fixtures_path=fixtures_path,
            allow_write_comments=config.safety.allow_write_comments,
            allow_open_pr=config.safety.allow_open_pr,
            dry_run=dry_run,
        )
    if config.tracker.kind == "local_file":
        return LocalFileTracker(
            path=loaded.resolve(config.tracker.path or "issues.json"),
            repo_root=loaded.repo_root,
            dry_run=dry_run,
        )
    if config.tracker.kind == "local_markdown":
        return LocalMarkdownTracker(
            path=loaded.resolve(config.tracker.path or "issues"),
            repo_root=loaded.repo_root,
            dry_run=dry_run,
        )
    raise ValueError(f"Unsupported tracker kind: {config.tracker.kind}")
