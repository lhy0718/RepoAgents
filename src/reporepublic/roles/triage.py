from reporepublic.models import TriageResult
from reporepublic.roles.base import BaseRole


class TriageRole(BaseRole[TriageResult]):
    name = "triage"
    output_model = TriageResult
