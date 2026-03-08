from reporepublic.models import QAResult
from reporepublic.roles.base import BaseRole


class QARole(BaseRole[QAResult]):
    name = "qa"
    output_model = QAResult
