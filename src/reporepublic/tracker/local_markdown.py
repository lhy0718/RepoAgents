from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from reporepublic.models import ExternalActionResult, IssueRef
from reporepublic.tracker.base import Tracker
from reporepublic.tracker.issue_loader import load_markdown_issue_directory
from reporepublic.utils.files import ensure_dir, write_json_file, write_text_file


class LocalMarkdownTracker(Tracker):
    def __init__(self, path: Path, repo_root: Path, dry_run: bool) -> None:
        self.path = path if path.is_absolute() else (repo_root / path).resolve()
        self.repo_root = repo_root
        self.dry_run = dry_run
        self.sync_root = repo_root / ".ai-republic" / "sync" / "local-markdown"

    async def list_open_issues(self) -> list[IssueRef]:
        return load_markdown_issue_directory(self.path)

    async def get_issue(self, issue_id: int) -> IssueRef:
        for issue in load_markdown_issue_directory(self.path):
            if issue.id == issue_id:
                return issue
        raise KeyError(f"Issue {issue_id} not found in local markdown tracker directory {self.path}.")

    async def post_comment(self, issue_id: int, body: str) -> ExternalActionResult:
        if self.dry_run:
            return ExternalActionResult(
                action="post_comment",
                executed=False,
                reason="Dry-run blocks local_markdown sync staging.",
                payload={"issue_id": issue_id, "path": str(self.path)},
            )
        stage_path = self._stage_markdown(
            issue_id,
            "comment",
            body,
            frontmatter={"issue_id": issue_id, "action": "post_comment"},
        )
        return ExternalActionResult(
            action="post_comment",
            executed=True,
            reason="Staged issue comment in local_markdown sync directory.",
            payload={"issue_id": issue_id, "path": str(self.path), "stage_path": str(stage_path)},
        )

    async def create_branch(
        self,
        issue_id: int,
        name: str,
        workspace_path: Path,
        commit_message: str,
    ) -> ExternalActionResult:
        if self.dry_run:
            return ExternalActionResult(
                action="create_branch",
                executed=False,
                reason="Dry-run blocks local_markdown branch proposal staging.",
                payload={"issue_id": issue_id, "path": str(self.path), "requested_name": name},
            )
        stage_path = self._stage_json(
            issue_id,
            "branch",
            {
                "issue_id": issue_id,
                "branch_name": name,
                "commit_message": commit_message,
                "workspace_path": str(workspace_path),
                "base_branch": "main",
            },
        )
        return ExternalActionResult(
            action="create_branch",
            executed=True,
            reason="Staged branch proposal in local_markdown sync directory.",
            payload={
                "issue_id": issue_id,
                "path": str(self.path),
                "requested_name": name,
                "stage_path": str(stage_path),
                "branch_name": name,
                "base_branch": "main",
            },
        )

    async def open_pr(
        self,
        issue_id: int,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        draft: bool = True,
    ) -> ExternalActionResult:
        if self.dry_run:
            return ExternalActionResult(
                action="open_pr",
                executed=False,
                reason="Dry-run blocks local_markdown draft PR staging.",
                payload={"issue_id": issue_id, "path": str(self.path)},
            )
        metadata_path = self._stage_json(
            issue_id,
            "pr",
            {
                "issue_id": issue_id,
                "title": title,
                "head_branch": head_branch,
                "base_branch": base_branch,
                "draft": draft,
            },
        )
        body_path = self._stage_markdown(
            issue_id,
            "pr-body",
            body,
            frontmatter={
                "issue_id": issue_id,
                "title": title,
                "head_branch": head_branch,
                "base_branch": base_branch,
                "draft": draft,
                "metadata_path": str(metadata_path),
            },
        )
        return ExternalActionResult(
            action="open_pr",
            executed=True,
            reason="Staged draft PR proposal in local_markdown sync directory.",
            payload={
                "issue_id": issue_id,
                "path": str(self.path),
                "stage_path": str(body_path),
                "metadata_path": str(metadata_path),
                "url": str(body_path),
            },
        )

    async def set_issue_label(self, issue_id: int, labels: list[str]) -> ExternalActionResult:
        if self.dry_run:
            return ExternalActionResult(
                action="set_issue_label",
                executed=False,
                reason="Dry-run blocks local_markdown label staging.",
                payload={"issue_id": issue_id, "path": str(self.path), "labels": labels},
            )
        stage_path = self._stage_json(
            issue_id,
            "labels",
            {
                "issue_id": issue_id,
                "labels": labels,
            },
        )
        return ExternalActionResult(
            action="set_issue_label",
            executed=True,
            reason="Staged label proposal in local_markdown sync directory.",
            payload={"issue_id": issue_id, "path": str(self.path), "labels": labels, "stage_path": str(stage_path)},
        )

    def _stage_json(self, issue_id: int, action: str, payload: dict[str, object]) -> Path:
        stamp = self._timestamp()
        target = self._stage_dir(issue_id) / f"{stamp}-{action}.json"
        write_json_file(target, self._stage_payload(action, payload, stamp))
        return target

    def _stage_markdown(
        self,
        issue_id: int,
        action: str,
        body: str,
        *,
        frontmatter: dict[str, object],
    ) -> Path:
        stamp = self._timestamp()
        target = self._stage_dir(issue_id) / f"{stamp}-{action}.md"
        metadata = dict(frontmatter)
        metadata.setdefault("issue_id", issue_id)
        metadata.setdefault("action", action)
        metadata["staged_at"] = stamp
        frontmatter_body = yaml.safe_dump(metadata, sort_keys=False).strip()
        write_text_file(
            target,
            f"---\n{frontmatter_body}\n---\n\n{body.rstrip()}\n",
        )
        return target

    def _stage_dir(self, issue_id: int) -> Path:
        return ensure_dir(self.sync_root / f"issue-{issue_id}")

    def _stage_payload(self, action: str, payload: dict[str, object], stamp: str) -> dict[str, object]:
        return {
            "action": action,
            "staged_at": stamp,
            **payload,
        }

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
