from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import os
from pathlib import Path

from repoagents.backend import BackendExecutionError, build_backend
from repoagents.config import LoadedConfig
from repoagents.logging import get_logger
from repoagents.models import (
    ApprovalActionProposal,
    ApprovalRequest,
    ApprovalStatus,
    IssueRef,
    PublicationMode,
    ReviewDecision,
    ReviewResult,
    RiskLevel,
    RunLifecycle,
    RunRecord,
    WorkerLifecycle,
    WorkerMode,
)
from repoagents.models.domain import utc_now
from repoagents.orchestrator.publication import PublicationDraft, PublicationRenderer
from repoagents.orchestrator.state import RunStateStore, WorkerStateStore
from repoagents.orchestrator.webhooks import WebhookDecision, parse_github_webhook
from repoagents.policies import evaluate_policy
from repoagents.prompts import PromptRenderer
from repoagents.roles import (
    PipelineContext,
    build_review_signals,
    build_role_sequence,
    evaluate_review_criteria,
    risk_rank,
)
from repoagents.tracker import build_tracker
from repoagents.utils import (
    ArtifactStore,
    build_diff_report,
    build_repo_context,
    ensure_dir,
    rank_duplicate_candidates,
    render_duplicate_candidates_context,
    sanitize_branch_name,
    write_json_file,
    write_text_file,
)
from repoagents.workspace import build_workspace_manager


@dataclass(slots=True)
class DryRunPreview:
    issue_id: int
    title: str
    selected: bool
    backend_mode: str
    roles_to_invoke: list[str]
    likely_files: list[str]
    blocked_side_effects: list[str]
    policy_summary: str
    summary: str
    comment_preview: str
    pr_title_preview: str
    pr_body_preview: str


class WorkerLeaseLostError(RuntimeError):
    """Raised when a worker no longer owns the active worker lease."""


class Orchestrator:
    def __init__(
        self,
        loaded: LoadedConfig,
        dry_run: bool = False,
        *,
        worker_mode: WorkerMode | None = None,
    ) -> None:
        self.loaded = loaded
        self.dry_run = dry_run
        self.worker_mode = worker_mode
        self.worker_id: str | None = None
        self.logger = get_logger("repoagents.orchestrator")
        ensure_dir(self.loaded.workspace_root)
        ensure_dir(self.loaded.artifacts_dir)
        ensure_dir(self.loaded.state_dir)

        self.tracker = build_tracker(loaded, dry_run=dry_run)
        self.backend = build_backend(loaded)
        self.renderer = PromptRenderer(loaded)
        self.artifacts = ArtifactStore(loaded.artifacts_dir)
        self.workspace_manager = build_workspace_manager(loaded)
        self.state_store = RunStateStore(loaded.state_dir / "runs.json")
        self.worker_state_store = WorkerStateStore(loaded.state_dir / "worker.json")
        recovered = self.state_store.recover_in_progress_runs()
        if recovered:
            self.logger.warning(
                "Recovered interrupted runs after process restart.",
                extra={"recovered_runs": [record.run_id for record in recovered]},
            )
        self.publication_renderer = PublicationRenderer()

        timeout = loaded.data.agent.role_timeout_seconds
        self.role_sequence = build_role_sequence(
            self.loaded.data.roles.enabled,
            backend=self.backend,
            renderer=self.renderer,
            artifacts=self.artifacts,
            timeout_seconds=timeout,
        )
        self.roles_by_name = {role.name: role for role in self.role_sequence}

    async def run_forever(self) -> None:
        poll = self.loaded.data.tracker.poll_interval_seconds
        worker_enabled = self.worker_mode is not None
        stop_reason = "Worker loop stopped."
        if worker_enabled and self.worker_mode is not None:
            self.worker_id = self._new_worker_id()
            self.worker_state_store.start(
                worker_id=self.worker_id,
                pid=os.getpid(),
                mode=self.worker_mode,
                poll_interval_seconds=poll,
            )
            self.logger.info(
                "Worker loop started.",
                extra={
                    "worker_id": self.worker_id,
                    "worker_mode": self.worker_mode.value,
                    "pid": os.getpid(),
                    "poll_interval_seconds": poll,
                },
            )
        try:
            while True:
                if worker_enabled and self.worker_id:
                    if not self.worker_state_store.holds_lease(self.worker_id):
                        stop_reason = "Worker lease lost to another process."
                        break
                    if self.worker_state_store.stop_requested(self.worker_id):
                        stop_reason = "Stop requested from service control command."
                        break
                    if self.worker_state_store.begin_poll(self.worker_id) is None:
                        stop_reason = "Worker lease lost to another process."
                        break
                try:
                    result = await self.run_once()
                except Exception as exc:
                    if worker_enabled and self.worker_id:
                        updated = self.worker_state_store.fail_poll(self.worker_id, error=str(exc))
                        if updated is None and isinstance(exc, WorkerLeaseLostError):
                            stop_reason = "Worker lease lost to another process."
                            break
                    raise
                if worker_enabled and self.worker_id:
                    updated = self.worker_state_store.complete_poll(self.worker_id, run_count=len(result))
                    if updated is None:
                        stop_reason = "Worker lease lost to another process."
                        break
                sleep_reason = await self._sleep_until_next_poll(poll)
                if sleep_reason is not None:
                    stop_reason = sleep_reason
                    break
        finally:
            if worker_enabled and self.worker_id:
                self.worker_state_store.mark_stopped(self.worker_id, reason=stop_reason)
                self.logger.info(
                    "Worker loop stopped.",
                    extra={"worker_id": self.worker_id, "worker_mode": self.worker_mode.value},
                )

    async def run_once(self) -> list[RunRecord] | list[DryRunPreview]:
        issues = await self.tracker.list_open_issues()
        candidates = [issue for issue in issues if self._is_runnable(issue)]
        if self.dry_run:
            previews: list[DryRunPreview] = []
            for issue in candidates[: self.loaded.data.agent.max_concurrent_runs]:
                previews.append(await self.preview_issue(issue, issues))
            return previews

        semaphore = asyncio.Semaphore(self.loaded.data.agent.max_concurrent_runs)
        tasks = [self._run_issue_guarded(issue, issues, semaphore) for issue in candidates]
        if not tasks:
            return []
        return await asyncio.gather(*tasks)

    async def run_issue_by_id(
        self,
        issue_id: int,
        *,
        force: bool = False,
    ) -> RunRecord | DryRunPreview | None:
        open_issues = await self.tracker.list_open_issues()
        detailed_issue = await self.tracker.get_issue(issue_id)
        if all(issue.id != detailed_issue.id for issue in open_issues):
            open_issues = [*open_issues, detailed_issue]
        if not force and not self._is_runnable(detailed_issue):
            self.logger.info(
                "Single issue run skipped because the issue is not currently runnable.",
                extra={"issue_id": issue_id, "dry_run": self.dry_run, "forced": force},
            )
            return None
        if self.dry_run:
            return await self.preview_issue(detailed_issue, open_issues)
        return await self._run_issue(detailed_issue, open_issues)

    async def handle_github_webhook(
        self,
        event: str,
        payload: dict,
        *,
        force: bool = False,
    ) -> tuple[WebhookDecision, RunRecord | DryRunPreview | None]:
        decision = parse_github_webhook(event, payload)
        if not decision.should_run or decision.issue_id is None:
            return decision, None
        result = await self.run_issue_by_id(decision.issue_id, force=force)
        return decision, result

    async def preview_issue(self, issue: IssueRef, open_issues: list[IssueRef]) -> DryRunPreview:
        detailed_issue = await self.tracker.get_issue(issue.id)
        run_id = self._new_run_id(issue.id, preview=True)
        workspace = await self.workspace_manager.prepare_workspace(detailed_issue, run_id)
        repo_context = build_repo_context(workspace)
        duplicate_candidates = rank_duplicate_candidates(detailed_issue, open_issues)
        context = PipelineContext(
            loaded=self.loaded,
            issue=detailed_issue,
            workspace_path=workspace,
            run_id=run_id,
            dry_run=True,
            repo_context=repo_context,
            duplicate_candidates_context=render_duplicate_candidates_context(duplicate_candidates),
            duplicate_candidates_hint=[candidate.to_metadata() for candidate in duplicate_candidates],
        )
        triage, _ = await self.roles_by_name["triage"].run(context)
        context.triage = triage
        plan, _ = await self.roles_by_name["planner"].run(context)
        policy_summary = (
            f"Merge policy default={self.loaded.data.merge_policy.mode.value}. "
            f"PR open allowed={self.loaded.data.safety.allow_open_pr}."
        )
        blocked_side_effects = [
            "Issue comments blocked in dry-run.",
            "Branch creation blocked in dry-run.",
            "PR opening blocked in dry-run.",
            "GitHub label writes blocked in dry-run.",
            "Engineer and reviewer Codex runs are previewed but not executed.",
        ]
        publication_draft = self.publication_renderer.build_preview_draft(
            issue_id=detailed_issue.id,
            issue_title=detailed_issue.title,
            triage_summary=triage.summary,
            plan_summary=plan.summary,
            likely_files=plan.likely_files,
            policy_summary=policy_summary,
        )
        return DryRunPreview(
            issue_id=detailed_issue.id,
            title=detailed_issue.title,
            selected=True,
            backend_mode=self.loaded.data.llm.mode.value,
            roles_to_invoke=[role.value for role in self.loaded.data.roles.enabled],
            likely_files=plan.likely_files,
            blocked_side_effects=blocked_side_effects,
            policy_summary=policy_summary,
            summary=f"{triage.summary} {plan.summary}",
            comment_preview=self.publication_renderer.render_issue_comment(publication_draft),
            pr_title_preview=self.publication_renderer.render_pr_title(publication_draft),
            pr_body_preview=self.publication_renderer.render_pr_body(publication_draft),
        )

    async def _run_issue_guarded(
        self,
        issue: IssueRef,
        open_issues: list[IssueRef],
        semaphore: asyncio.Semaphore,
    ) -> RunRecord:
        async with semaphore:
            detailed_issue = await self.tracker.get_issue(issue.id)
            return await self._run_issue(detailed_issue, open_issues)

    async def _run_issue(self, issue: IssueRef, open_issues: list[IssueRef]) -> RunRecord:
        previous = self.state_store.get(issue.id)
        run_id = self._new_run_id(issue.id)
        attempts = (previous.attempts if previous else 0) + 1
        record = RunRecord(
            run_id=run_id,
            issue_id=issue.id,
            issue_title=issue.title,
            fingerprint=issue.fingerprint(),
            status=RunLifecycle.IN_PROGRESS,
            attempts=attempts,
            dry_run=False,
            backend_mode=self.loaded.data.llm.mode.value,
        )
        self.state_store.upsert(record)
        self.logger.info(
            "Issue run started.",
            extra=self._run_log_extra(record),
        )

        try:
            self._ensure_worker_lease(record=record, stage="preparing workspace")
            workspace = await self.workspace_manager.prepare_workspace(issue, run_id)
            record.workspace_path = str(workspace)
            self.state_store.upsert(record)
            self._ensure_worker_lease(record=record, stage="building repo context")
            repo_context = build_repo_context(workspace)
            duplicate_candidates = rank_duplicate_candidates(issue, open_issues)
            context = PipelineContext(
                loaded=self.loaded,
                issue=issue,
                workspace_path=workspace,
                run_id=run_id,
                dry_run=False,
                repo_context=repo_context,
                duplicate_candidates_context=render_duplicate_candidates_context(duplicate_candidates),
                duplicate_candidates_hint=[candidate.to_metadata() for candidate in duplicate_candidates],
            )

            policy = None
            reviewer = None
            for role in self.role_sequence:
                result = await self._run_role(record, role, context)
                if role.name == "triage":
                    context.triage = result
                elif role.name == "planner":
                    context.plan = result
                elif role.name == "engineer":
                    context.engineering = result
                    context.diff_report = build_diff_report(self.loaded.repo_root, workspace)
                    policy = evaluate_policy(
                        context.triage.issue_type,
                        context.diff_report,
                        self.loaded.data.auto_merge.allowed_types,
                        requested_publication_mode=self.loaded.data.merge_policy.mode,
                    )
                    context.policy_findings = policy.findings
                elif role.name == "reviewer":
                    reviewer = result
                else:
                    context.extra_role_results[role.name] = result.model_dump(mode="json")

            triage = context.triage
            plan = context.plan
            engineering = context.engineering
            if triage is None or plan is None or engineering is None or reviewer is None or policy is None:
                raise RuntimeError("Configured role sequence did not produce the required core role outputs.")
            final_review = self._apply_review_overrides(
                reviewer=reviewer,
                review_signals=build_review_signals(context.plan, context.engineering, context.diff_report),
                policy_findings=policy.findings,
            )

            record.status = RunLifecycle.COMPLETED
            record.current_role = None
            record.finished_at = utc_now()
            record.summary = (
                f"{triage.summary} {plan.summary} {engineering.summary} "
                f"{final_review.summary} {policy.summary}"
            )
            publication_draft = self._build_publication_draft(
                issue=issue,
                triage=triage,
                plan=plan,
                engineering=engineering,
                review=final_review,
                policy_summary=policy.summary,
                preview_only=False,
            )
            published_pr_url = None
            if policy.publication_mode == PublicationMode.HUMAN_APPROVAL and final_review.decision == ReviewDecision.APPROVE:
                self._ensure_worker_lease(record=record, stage="staging approval request")
                record.approval_request = self._create_approval_request(
                    record=record,
                    issue=issue,
                    engineering=engineering,
                    review=final_review,
                    draft=publication_draft,
                    policy_summary=policy.summary,
                )
            else:
                record.approval_request = None
                self._ensure_worker_lease(record=record, stage="publishing changes")
                published_pr_url = await self._publish_changes(
                    record=record,
                    issue=issue,
                    workspace=workspace,
                    triage=triage,
                    plan=plan,
                    engineering=engineering,
                    review=final_review,
                    policy_summary=policy.summary,
                    publication_mode=policy.publication_mode,
                )
                if published_pr_url:
                    publication_draft.pr_url = published_pr_url
            self.state_store.upsert(record)
            self.logger.info(
                "Issue run completed.",
                extra=self._run_log_extra(record),
            )

            if self.loaded.data.safety.allow_write_comments and record.approval_request is None:
                self._ensure_worker_lease(record=record, stage="posting issue comment")
                comment_result = await self.tracker.post_comment(
                    issue.id,
                    self.publication_renderer.render_issue_comment(publication_draft),
                )
                record.external_actions.append(comment_result)
                self.state_store.upsert(record)
            return record
        except Exception as exc:  # noqa: BLE001
            record.last_error = str(exc)
            record.current_role = None
            record.finished_at = utc_now()
            if isinstance(exc, WorkerLeaseLostError):
                record.status = RunLifecycle.RETRY_PENDING
                record.next_retry_at = utc_now()
            else:
                backoff = self.loaded.data.agent.base_retry_seconds * (2 ** (attempts - 1))
                if attempts >= self.loaded.data.agent.retry_limit:
                    record.status = RunLifecycle.FAILED
                    record.next_retry_at = None
                else:
                    record.status = RunLifecycle.RETRY_PENDING
                    record.next_retry_at = utc_now() + timedelta(seconds=backoff)
            self.state_store.upsert(record)
            if isinstance(exc, WorkerLeaseLostError):
                self.logger.warning(
                    "Issue run requeued after worker lease loss.",
                    extra=self._run_log_extra(record),
                )
            else:
                self.logger.error(
                    "Issue run failed.",
                    extra=self._run_log_extra(record),
                    exc_info=exc,
                )
            return record

    async def _run_role(self, record: RunRecord, role, context: PipelineContext):
        self._ensure_worker_lease(record=record, stage=f"starting role {role.name}")
        record.current_role = role.name
        self.state_store.upsert(record)
        self.logger.info(
            "Role started.",
            extra=self._run_log_extra(record, role=role.name),
        )
        result, artifacts = await role.run(context)
        self._ensure_worker_lease(record=record, stage=f"completing role {role.name}")
        record.role_artifacts[role.name] = artifacts["markdown"]
        self.state_store.upsert(record)
        self.logger.info(
            "Role completed.",
            extra=self._run_log_extra(record, role=role.name),
        )
        return result

    def _apply_review_overrides(
        self,
        reviewer: ReviewResult,
        review_signals,
        policy_findings: list[str],
    ) -> ReviewResult:
        criteria = evaluate_review_criteria(review_signals, policy_findings)
        merged_notes = reviewer.review_notes.copy()
        for note in [*criteria.must_fix, *criteria.watch_items]:
            if note not in merged_notes:
                merged_notes.append(note)

        merged_risk = reviewer.risk_level
        if risk_rank(criteria.risk_level) > risk_rank(reviewer.risk_level):
            merged_risk = criteria.risk_level

        if criteria.decision == ReviewDecision.REQUEST_CHANGES and reviewer.decision != ReviewDecision.REQUEST_CHANGES:
            return ReviewResult(
                decision=ReviewDecision.REQUEST_CHANGES,
                risk_level=RiskLevel.HIGH,
                review_notes=merged_notes,
                summary="Reviewer decision overridden to request_changes by RepoAgents review criteria.",
            )

        if merged_notes != reviewer.review_notes or merged_risk != reviewer.risk_level:
            return ReviewResult(
                decision=reviewer.decision,
                risk_level=merged_risk,
                review_notes=merged_notes,
                summary=reviewer.summary,
            )

        return reviewer

    def _is_runnable(self, issue: IssueRef) -> bool:
        record = self.state_store.get(issue.id)
        if record is None:
            return True
        now = utc_now()
        if record.status == RunLifecycle.IN_PROGRESS:
            return False
        if record.fingerprint == issue.fingerprint() and record.status == RunLifecycle.COMPLETED:
            return False
        if record.status in {RunLifecycle.RETRY_PENDING, RunLifecycle.FAILED}:
            if record.next_retry_at and record.next_retry_at > now:
                return False
            return True
        return True

    def _new_run_id(self, issue_id: int, preview: bool = False) -> str:
        stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        prefix = "preview" if preview else "run"
        return f"{prefix}-{issue_id}-{stamp}"

    def _new_worker_id(self) -> str:
        stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        return f"worker-{os.getpid()}-{stamp}"

    async def _sleep_until_next_poll(self, poll_interval_seconds: int) -> str | None:
        if poll_interval_seconds <= 0:
            return None
        deadline = asyncio.get_running_loop().time() + poll_interval_seconds
        while True:
            if self.worker_id:
                if not self.worker_state_store.holds_lease(self.worker_id):
                    return "Worker lease lost to another process."
                if self.worker_state_store.stop_requested(self.worker_id):
                    return "Stop requested from service control command."
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return None
            if self.worker_id and self.worker_state_store.heartbeat(
                self.worker_id,
                status=WorkerLifecycle.IDLE,
            ) is None:
                return "Worker lease lost to another process."
            await asyncio.sleep(min(1.0, remaining))

    async def _publish_changes(
        self,
        record: RunRecord,
        issue: IssueRef,
        workspace: Path,
        triage,
        plan,
        engineering,
        review: ReviewResult,
        policy_summary: str,
        publication_mode: PublicationMode,
    ) -> str | None:
        if publication_mode == PublicationMode.COMMENT_ONLY:
            return None
        if not self.loaded.data.safety.allow_open_pr:
            return None
        if not engineering.changed_files:
            return None
        if review.decision != ReviewDecision.APPROVE:
            return None

        self._ensure_worker_lease(record=record, stage="creating branch")
        branch_result = await self.tracker.create_branch(
            issue_id=issue.id,
            name=self._build_branch_name(issue, record.run_id),
            workspace_path=workspace,
            commit_message=f"repoagents: address issue #{issue.id}",
        )
        record.external_actions.append(branch_result)
        self.state_store.upsert(record)
        if not branch_result.executed:
            return None

        self._ensure_worker_lease(record=record, stage="opening pull request")
        pr_result = await self.tracker.open_pr(
            issue_id=issue.id,
            title=self.publication_renderer.render_pr_title(
                self._build_publication_draft(
                    issue=issue,
                    triage=triage,
                    plan=plan,
                    engineering=engineering,
                    review=review,
                    policy_summary=policy_summary,
                    preview_only=False,
                )
            ),
            body=self.publication_renderer.render_pr_body(
                self._build_publication_draft(
                    issue=issue,
                    triage=triage,
                    plan=plan,
                    engineering=engineering,
                    review=review,
                    policy_summary=policy_summary,
                    preview_only=False,
                )
            ),
            head_branch=branch_result.payload["branch_name"],
            base_branch=branch_result.payload["base_branch"],
            draft=True,
        )
        record.external_actions.append(pr_result)
        self.state_store.upsert(record)
        return pr_result.payload.get("url")

    def _create_approval_request(
        self,
        *,
        record: RunRecord,
        issue: IssueRef,
        engineering,
        review: ReviewResult,
        draft: PublicationDraft,
        policy_summary: str,
    ) -> ApprovalRequest | None:
        artifact_dir = self.artifacts.role_dir(issue.id, record.run_id)
        actions: list[ApprovalActionProposal] = []

        if self.loaded.data.safety.allow_write_comments:
            comment_path = artifact_dir / "approval-comment.md"
            write_text_file(comment_path, self.publication_renderer.render_issue_comment(draft))
            record.role_artifacts["approval-comment"] = str(comment_path)
            actions.append(
                ApprovalActionProposal(
                    action="post_comment",
                    summary="Post the generated issue comment after maintainer approval.",
                    payload={"artifact_path": str(comment_path)},
                )
            )

        if self.loaded.data.safety.allow_open_pr and engineering.changed_files and review.decision == ReviewDecision.APPROVE:
            branch_name = self._build_branch_name(issue, record.run_id)
            pr_title = self.publication_renderer.render_pr_title(draft)
            pr_body_path = artifact_dir / "approval-pr-body.md"
            pr_metadata_path = artifact_dir / "approval-pr.json"
            write_text_file(pr_body_path, self.publication_renderer.render_pr_body(draft))
            write_json_file(
                pr_metadata_path,
                {
                    "issue_id": issue.id,
                    "branch_name": branch_name,
                    "title": pr_title,
                    "draft": True,
                },
            )
            record.role_artifacts["approval-pr-body"] = str(pr_body_path)
            actions.extend(
                [
                    ApprovalActionProposal(
                        action="create_branch",
                        summary="Create and push the proposed branch after maintainer approval.",
                        payload={
                            "branch_name": branch_name,
                            "commit_message": f"repoagents: address issue #{issue.id}",
                        },
                    ),
                    ApprovalActionProposal(
                        action="open_pr",
                        summary="Open the generated draft pull request after maintainer approval.",
                        payload={
                            "title": pr_title,
                            "body_artifact_path": str(pr_body_path),
                            "metadata_artifact_path": str(pr_metadata_path),
                            "draft": True,
                        },
                    ),
                ]
            )

        if not actions:
            return None

        request = ApprovalRequest(
            summary="Maintainer approval is required before RepoAgents performs queued publication actions.",
            policy_summary=policy_summary,
            review_summary=review.summary,
            actions=actions,
        )
        request_path = artifact_dir / "approval-request.md"
        request.request_artifact_path = str(request_path)
        write_text_file(request_path, self._render_approval_request_markdown(record=record, request=request))
        write_json_file(artifact_dir / "approval-request.json", request.model_dump(mode="json"))
        record.role_artifacts["approval-request"] = str(request_path)
        return request

    def _render_approval_request_markdown(
        self,
        *,
        record: RunRecord,
        request: ApprovalRequest,
    ) -> str:
        lines = [
            "# Approval Request",
            "",
            f"- issue: #{record.issue_id} {record.issue_title}",
            f"- run_id: {record.run_id}",
            f"- status: {request.status.value}",
            f"- requested_at: {request.requested_at.isoformat()}",
            f"- publication_mode: {request.publication_mode.value}",
            f"- policy: {request.policy_summary}",
            f"- review: {request.review_summary}",
            "",
            "## Proposed actions",
        ]
        for action in request.actions:
            lines.append(f"- {action.action}: {action.summary}")
            for key, value in sorted(action.payload.items()):
                lines.append(f"  - {key}: {value}")
        return "\n".join(lines) + "\n"

    def _ensure_worker_lease(self, *, record: RunRecord, stage: str) -> None:
        if self.worker_mode is None or self.worker_id is None:
            return
        if self.worker_state_store.holds_lease(self.worker_id):
            return
        self.logger.warning(
            "Worker lease lost; requeueing issue.",
            extra={
                "worker_id": self.worker_id,
                "worker_mode": self.worker_mode.value,
                "issue_id": record.issue_id,
                "run_id": record.run_id,
                "stage": stage,
            },
        )
        raise WorkerLeaseLostError(f"Worker lease lost during {stage}; requeueing current issue.")

    def _build_publication_draft(
        self,
        issue: IssueRef,
        triage,
        plan,
        engineering,
        review: ReviewResult,
        policy_summary: str,
        pr_url: str | None = None,
        preview_only: bool = False,
    ) -> PublicationDraft:
        return PublicationDraft(
            issue_id=issue.id,
            issue_title=issue.title,
            triage_summary=triage.summary,
            plan_summary=plan.summary,
            patch_summary=engineering.patch_summary,
            review_summary=review.summary,
            decision=review.decision.value,
            risk_level=review.risk_level.value,
            policy_summary=policy_summary,
            changed_files=engineering.changed_files,
            test_actions=engineering.test_actions,
            review_notes=review.review_notes,
            pr_url=pr_url,
            preview_only=preview_only,
        )

    def _build_branch_name(self, issue: IssueRef, run_id: str) -> str:
        slug = sanitize_branch_name(issue.title, issue_id=issue.id).split("/", 1)[-1]
        suffix = run_id[-15:].lower().replace(":", "").replace("/", "-")
        return sanitize_branch_name(
            f"repoagents/issue-{issue.id}-{slug}-{suffix}",
            issue_id=issue.id,
        )

    def _run_log_extra(self, record: RunRecord, role: str | None = None) -> dict[str, str | int | None]:
        return {
            "run_id": record.run_id,
            "issue_id": record.issue_id,
            "status": record.status.value,
            "role": role or record.current_role,
        }
