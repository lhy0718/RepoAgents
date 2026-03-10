from repoagents.models import PlanResult
from repoagents.roles.base import BaseRole


class PlannerRole(BaseRole[PlanResult]):
    name = "planner"
    output_model = PlanResult
