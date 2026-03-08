from reporepublic.models import EngineeringResult
from reporepublic.roles.base import BaseRole


class EngineerRole(BaseRole[EngineeringResult]):
    name = "engineer"
    output_model = EngineeringResult
    allow_write = True
