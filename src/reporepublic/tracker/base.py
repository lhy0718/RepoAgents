from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from reporepublic.models import ExternalActionResult, IssueRef


class Tracker(ABC):
    @abstractmethod
    async def list_open_issues(self) -> list[IssueRef]:
        raise NotImplementedError

    @abstractmethod
    async def get_issue(self, issue_id: int) -> IssueRef:
        raise NotImplementedError

    @abstractmethod
    async def post_comment(self, issue_id: int, body: str) -> ExternalActionResult:
        raise NotImplementedError

    @abstractmethod
    async def create_branch(
        self,
        issue_id: int,
        name: str,
        workspace_path: Path,
        commit_message: str,
    ) -> ExternalActionResult:
        raise NotImplementedError

    @abstractmethod
    async def open_pr(
        self,
        issue_id: int,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        draft: bool = True,
    ) -> ExternalActionResult:
        raise NotImplementedError

    @abstractmethod
    async def set_issue_label(self, issue_id: int, labels: list[str]) -> ExternalActionResult:
        raise NotImplementedError
