from repoagents.models import QAResult
from repoagents.roles.base import BaseRole


class QARole(BaseRole[QAResult]):
    name = "qa"
    output_model = QAResult
