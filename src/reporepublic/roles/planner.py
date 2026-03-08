from reporepublic.models import PlanResult
from reporepublic.roles.base import BaseRole


class PlannerRole(BaseRole[PlanResult]):
    name = "planner"
    output_model = PlanResult
