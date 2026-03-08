from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from reporepublic.config.models import RepoRepublicConfig


DEFAULT_CONFIG_PATH = Path(".ai-republic/reporepublic.yaml")


class ConfigLoadError(RuntimeError):
    """Raised when RepoRepublic config cannot be loaded."""


@dataclass(slots=True)
class LoadedConfig:
    repo_root: Path
    config_path: Path
    data: RepoRepublicConfig

    @property
    def ai_root(self) -> Path:
        return self.config_path.parent

    @property
    def workspace_root(self) -> Path:
        return resolve_path(self.repo_root, self.data.workspace.root)

    @property
    def state_dir(self) -> Path:
        return self.ai_root / "state"

    @property
    def artifacts_dir(self) -> Path:
        return self.ai_root / "artifacts"

    @property
    def reports_dir(self) -> Path:
        return self.ai_root / "reports"

    @property
    def sync_dir(self) -> Path:
        return self.ai_root / "sync"

    @property
    def sync_applied_dir(self) -> Path:
        return self.ai_root / "sync-applied"

    @property
    def logs_dir(self) -> Path:
        return resolve_path(self.repo_root, self.data.logging.directory)

    def resolve(self, raw_path: str | Path) -> Path:
        return resolve_path(self.repo_root, raw_path)


def resolve_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / DEFAULT_CONFIG_PATH).exists():
            return candidate
    return current


def resolve_path(base: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (base / path).resolve()


def load_config(repo_root: Path | None = None, config_path: Path | None = None) -> LoadedConfig:
    root = (repo_root or resolve_repo_root()).resolve()
    path = (config_path or (root / DEFAULT_CONFIG_PATH)).resolve()
    if not path.exists():
        raise ConfigLoadError(
            f"RepoRepublic config not found at {path}. Run `republic init` first."
        )
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"Could not parse YAML at {path}: {exc}") from exc
    try:
        config = RepoRepublicConfig.model_validate(payload)
    except ValidationError as exc:
        raise ConfigLoadError(format_validation_error(path, exc)) from exc
    return LoadedConfig(repo_root=root, config_path=path, data=config)


def format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"Invalid RepoRepublic config at {path}:"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        message = error["msg"]
        lines.append(f"- {location}: {message}")
    return "\n".join(lines)
