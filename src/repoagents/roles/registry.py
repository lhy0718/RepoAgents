from __future__ import annotations

from collections.abc import Sequence

from repoagents.backend import BackendRunner
from repoagents.models import RoleName
from repoagents.prompts import PromptRenderer
from repoagents.roles.base import BaseRole
from repoagents.roles.engineer import EngineerRole
from repoagents.roles.planner import PlannerRole
from repoagents.roles.qa import QARole
from repoagents.roles.reviewer import ReviewerRole
from repoagents.roles.triage import TriageRole
from repoagents.utils import ArtifactStore


ROLE_REGISTRY: dict[RoleName, type[BaseRole]] = {
    RoleName.TRIAGE: TriageRole,
    RoleName.PLANNER: PlannerRole,
    RoleName.ENGINEER: EngineerRole,
    RoleName.QA: QARole,
    RoleName.REVIEWER: ReviewerRole,
}


def build_role_sequence(
    enabled_roles: Sequence[RoleName],
    *,
    backend: BackendRunner,
    renderer: PromptRenderer,
    artifacts: ArtifactStore,
    timeout_seconds: int,
) -> list[BaseRole]:
    roles: list[BaseRole] = []
    for role_name in enabled_roles:
        role_cls = ROLE_REGISTRY.get(role_name)
        if role_cls is None:
            raise ValueError(f"Unsupported role configured: {role_name.value}")
        roles.append(role_cls(backend, renderer, artifacts, timeout_seconds))
    return roles
