from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from reporepublic.backend import BackendExecutionError, build_backend
from reporepublic.config import LoadedConfig
from reporepublic.logging import get_logger
from reporepublic.models import (
    IssueRef,
    PublicationMode,
    ReviewDecision,
    ReviewResult,
    RiskLevel,
    RunLifecycle,
    RunRecord,
)
from reporepublic.models.domain import utc_now
from reporepublic.orchestrator.publication import PublicationDraft, PublicationRenderer
from reporepublic.orchestrator.state import RunStateStore
from reporepublic.orchestrator.webhooks import WebhookDecision, parse_github_webhook
from reporepublic.policies import evaluate_policy
from reporepublic.prompts import PromptRenderer
from reporepublic.roles import (
    PipelineContext,
    build_review_signals,
    build_role_sequence,
    evaluate_review_criteria,
    risk_rank,
)
from reporepublic.tracker import build_tracker
from reporepublic.utils import (
    ArtifactStore,
    build_diff_report,
    build_repo_context,
    ensure_dir,
    rank_duplicate_candidates,
    render_duplicate_candidates_context,
    sanitize_branch_name,
)
from reporepublic.workspace import build_workspace_manager


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


class Orchestrator:
    def __init__(self, loaded: LoadedConfig, dry_run: bool = False) -> None:
        self.loaded = loaded
        self.dry_run = dry_run
        self.logger = get_logger("reporepublic.orchestrator")
        ensure_dir(self.loaded.workspace_root)
        ensure_dir(self.loaded.artifacts_dir)
        ensure_dir(self.loaded.state_dir)

        self.tracker = build_tracker(loaded, dry_run=dry_run)
        self.backend = build_backend(loaded)
        self.renderer = PromptRenderer(loaded)
        self.artifacts = ArtifactStore(loaded.artifacts_dir)
        self.workspace_manager = build_workspace_manager(loaded)
        self.state_store = RunStateStore(loaded.state_dir / "runs.json")
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
        while True:
            await self.run_once()
            await asyncio.sleep(poll)

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
            workspace = await self.workspace_manager.prepare_workspace(issue, run_id)
            record.workspace_path = str(workspace)
            self.state_store.upsert(record)
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
            self.state_store.upsert(record)
            self.logger.info(
                "Issue run completed.",
                extra=self._run_log_extra(record),
            )

            if self.loaded.data.safety.allow_write_comments:
                comment_result = await self.tracker.post_comment(
                    issue.id,
                    self.publication_renderer.render_issue_comment(
                        self._build_publication_draft(
                            issue=issue,
                            triage=triage,
                            plan=plan,
                            engineering=engineering,
                            review=final_review,
                            policy_summary=policy.summary,
                            pr_url=published_pr_url,
                            preview_only=False,
                        )
                    ),
                )
                record.external_actions.append(comment_result)
                self.state_store.upsert(record)
            return record
        except Exception as exc:  # noqa: BLE001
            backoff = self.loaded.data.agent.base_retry_seconds * (2 ** (attempts - 1))
            record.last_error = str(exc)
            record.current_role = None
            record.finished_at = utc_now()
            if attempts >= self.loaded.data.agent.retry_limit:
                record.status = RunLifecycle.FAILED
                record.next_retry_at = None
            else:
                record.status = RunLifecycle.RETRY_PENDING
                record.next_retry_at = utc_now() + timedelta(seconds=backoff)
            self.state_store.upsert(record)
            self.logger.error(
                "Issue run failed.",
                extra=self._run_log_extra(record),
                exc_info=exc,
            )
            return record

    async def _run_role(self, record: RunRecord, role, context: PipelineContext):
        record.current_role = role.name
        self.state_store.upsert(record)
        self.logger.info(
            "Role started.",
            extra=self._run_log_extra(record, role=role.name),
        )
        result, artifacts = await role.run(context)
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
                summary="Reviewer decision overridden to request_changes by RepoRepublic review criteria.",
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

        branch_result = await self.tracker.create_branch(
            issue_id=issue.id,
            name=self._build_branch_name(issue, record.run_id),
            workspace_path=workspace,
            commit_message=f"republic: address issue #{issue.id}",
        )
        record.external_actions.append(branch_result)
        self.state_store.upsert(record)
        if not branch_result.executed:
            return None

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
            f"reporepublic/issue-{issue.id}-{slug}-{suffix}",
            issue_id=issue.id,
        )

    def _run_log_extra(self, record: RunRecord, role: str | None = None) -> dict[str, str | int | None]:
        return {
            "run_id": record.run_id,
            "issue_id": record.issue_id,
            "status": record.status.value,
            "role": role or record.current_role,
        }
