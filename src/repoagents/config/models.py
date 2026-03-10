from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from repoagents.models import PublicationMode, RoleName


class TrackerMode(StrEnum):
    REST = "rest"
    FIXTURE = "fixture"


class TrackerKind(StrEnum):
    GITHUB = "github"
    LOCAL_FILE = "local_file"
    LOCAL_MARKDOWN = "local_markdown"


class LLMMode(StrEnum):
    CODEX = "codex"
    MOCK = "mock"


class DirtyRepoPolicy(StrEnum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


class TrackerSettings(BaseModel):
    kind: TrackerKind = TrackerKind.GITHUB
    repo: str | None = None
    path: str | None = None
    poll_interval_seconds: int = Field(default=60, ge=5, le=3600)
    mode: TrackerMode = TrackerMode.REST
    api_url: str = "https://api.github.com"
    token_env: str = "GITHUB_TOKEN"
    fixtures_path: str | None = None
    smoke_fixture_path: str | None = None

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = value.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("tracker.repo must look like 'owner/name'")
        return value

    @model_validator(mode="after")
    def validate_fixture_mode(self) -> "TrackerSettings":
        if self.kind == TrackerKind.GITHUB:
            if not self.repo:
                raise ValueError("tracker.repo is required when tracker.kind=github")
            if self.mode == TrackerMode.FIXTURE and not self.fixtures_path:
                raise ValueError("tracker.fixtures_path is required when tracker.mode=fixture")
            return self

        if self.smoke_fixture_path:
            raise ValueError(
                f"tracker.smoke_fixture_path is only supported when tracker.kind={TrackerKind.GITHUB.value}"
            )
        if not self.path:
            if self.fixtures_path:
                self.path = self.fixtures_path
            else:
                raise ValueError(f"tracker.path is required when tracker.kind={self.kind.value}")
        return self


class WorkspaceSettings(BaseModel):
    root: str = "./.ai-repoagents/workspaces"
    strategy: Literal["copy", "worktree"] = "copy"
    dirty_policy: DirtyRepoPolicy = DirtyRepoPolicy.WARN


class AgentSettings(BaseModel):
    max_concurrent_runs: int = Field(default=2, ge=1, le=16)
    max_turns: int = Field(default=20, ge=1, le=100)
    role_timeout_seconds: int = Field(default=900, ge=30, le=7200)
    retry_limit: int = Field(default=3, ge=1, le=10)
    base_retry_seconds: int = Field(default=30, ge=5, le=3600)
    debug_artifacts: bool = False


class RolesSettings(BaseModel):
    enabled: list[RoleName] = Field(
        default_factory=lambda: [
            RoleName.TRIAGE,
            RoleName.PLANNER,
            RoleName.ENGINEER,
            RoleName.REVIEWER,
        ]
    )

    @field_validator("enabled")
    @classmethod
    def validate_enabled(cls, value: list[RoleName]) -> list[RoleName]:
        if len(value) != len(set(value)):
            raise ValueError("roles.enabled must not contain duplicate role names")
        required = {
            RoleName.TRIAGE,
            RoleName.PLANNER,
            RoleName.ENGINEER,
            RoleName.REVIEWER,
        }
        if not required.issubset(set(value)):
            missing = ", ".join(sorted(role.value for role in required.difference(value)))
            raise ValueError(f"roles.enabled must include all MVP roles: {missing}")
        order = {role: index for index, role in enumerate(value)}
        required_sequence = [
            RoleName.TRIAGE,
            RoleName.PLANNER,
            RoleName.ENGINEER,
            RoleName.REVIEWER,
        ]
        for left, right in zip(required_sequence, required_sequence[1:], strict=False):
            if order[left] >= order[right]:
                raise ValueError(
                    "roles.enabled must preserve core order: triage -> planner -> engineer -> reviewer"
                )
        if RoleName.QA in order:
            if not (order[RoleName.ENGINEER] < order[RoleName.QA] < order[RoleName.REVIEWER]):
                raise ValueError("roles.enabled must place qa after engineer and before reviewer")
        return value


class MergePolicySettings(BaseModel):
    mode: PublicationMode = PublicationMode.HUMAN_APPROVAL


class AutoMergeSettings(BaseModel):
    allowed_types: list[str] = Field(default_factory=lambda: ["docs", "tests"])


class SafetySettings(BaseModel):
    allow_write_comments: bool = True
    allow_open_pr: bool = False


class LLMSettings(BaseModel):
    mode: LLMMode = LLMMode.CODEX


class CodexSettings(BaseModel):
    command: str = "codex"
    model: str = "gpt-5.4"
    use_agents_md: bool = True
    sandbox: Literal["read-only", "workspace-write", "danger-full-access"] = "workspace-write"
    approval_policy: Literal["never", "on-request", "untrusted"] = "never"
    extra_args: list[str] = Field(default_factory=list)


class LoggingSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    json_logs: bool = Field(default=True, alias="json")
    level: str = "INFO"
    file_enabled: bool = False
    directory: str = "./.ai-repoagents/logs"

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
        normalized = value.upper()
        if normalized not in allowed:
            raise ValueError(f"logging.level must be one of: {', '.join(sorted(allowed))}")
        return normalized


class CleanupSettings(BaseModel):
    sync_applied_keep_groups_per_issue: int = Field(default=20, ge=1, le=500)
    ops_snapshot_keep_entries: int = Field(default=25, ge=1, le=500)
    ops_snapshot_prune_managed: bool = False


class ReportFreshnessPolicySettings(BaseModel):
    unknown_issues_threshold: int = Field(default=1, ge=1, le=1000)
    stale_issues_threshold: int = Field(default=1, ge=1, le=1000)
    future_attention_threshold: int = Field(default=1, ge=1, le=1000)
    aging_attention_threshold: int = Field(default=1, ge=1, le=1000)


class DashboardSettings(BaseModel):
    report_freshness_policy: ReportFreshnessPolicySettings = Field(
        default_factory=ReportFreshnessPolicySettings
    )


class RepoAgentsConfig(BaseModel):
    tracker: TrackerSettings
    workspace: WorkspaceSettings = Field(default_factory=WorkspaceSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    roles: RolesSettings = Field(default_factory=RolesSettings)
    merge_policy: MergePolicySettings = Field(default_factory=MergePolicySettings)
    auto_merge: AutoMergeSettings = Field(default_factory=AutoMergeSettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    codex: CodexSettings = Field(default_factory=CodexSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    cleanup: CleanupSettings = Field(default_factory=CleanupSettings)
    dashboard: DashboardSettings = Field(default_factory=DashboardSettings)

    @model_validator(mode="after")
    def validate_cross_section(self) -> "RepoAgentsConfig":
        if self.llm.mode == LLMMode.CODEX and not self.codex.command.strip():
            raise ValueError("codex.command must not be empty when llm.mode=codex")
        return self

    @field_validator("workspace")
    @classmethod
    def validate_workspace(cls, value: WorkspaceSettings, info: ValidationInfo) -> WorkspaceSettings:
        if not Path(value.root).as_posix():
            raise ValueError("workspace.root must be a valid path")
        return value
