from repoagents.models import EngineeringResult
from repoagents.roles.base import BaseRole


class EngineerRole(BaseRole[EngineeringResult]):
    name = "engineer"
    output_model = EngineeringResult
    allow_write = True
