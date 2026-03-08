from reporepublic.models import ReviewResult
from reporepublic.roles.base import BaseRole


class ReviewerRole(BaseRole[ReviewResult]):
    name = "reviewer"
    output_model = ReviewResult
