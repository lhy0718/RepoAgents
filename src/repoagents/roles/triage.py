from repoagents.models import TriageResult
from repoagents.roles.base import BaseRole


class TriageRole(BaseRole[TriageResult]):
    name = "triage"
    output_model = TriageResult
