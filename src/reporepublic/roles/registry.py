from __future__ import annotations

from collections.abc import Sequence

from reporepublic.backend import BackendRunner
from reporepublic.models import RoleName
from reporepublic.prompts import PromptRenderer
from reporepublic.roles.base import BaseRole
from reporepublic.roles.engineer import EngineerRole
from reporepublic.roles.planner import PlannerRole
from reporepublic.roles.qa import QARole
from reporepublic.roles.reviewer import ReviewerRole
from reporepublic.roles.triage import TriageRole
from reporepublic.utils import ArtifactStore


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
