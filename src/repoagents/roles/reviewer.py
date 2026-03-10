from repoagents.models import ReviewResult
from repoagents.roles.base import BaseRole


class ReviewerRole(BaseRole[ReviewResult]):
    name = "reviewer"
    output_model = ReviewResult
