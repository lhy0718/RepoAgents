from __future__ import annotations

import json
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

from reporepublic.backend import BackendInvocation, BackendRunner
from reporepublic.config import LoadedConfig
from reporepublic.models import DiffReport, EngineeringResult, IssueRef, PlanResult, TriageResult
from reporepublic.prompts import PromptRenderer
from reporepublic.roles.review_criteria import evaluate_review_criteria
from reporepublic.roles.review_signals import build_review_signals
from reporepublic.utils import ArtifactStore


RoleResultT = TypeVar("RoleResultT", bound=BaseModel)


@dataclass(slots=True)
class PipelineContext:
    loaded: LoadedConfig
    issue: IssueRef
    workspace_path: Path
    run_id: str
    dry_run: bool
    repo_context: str
    duplicate_candidates_context: str = "- No strong duplicate candidates found among current open issues."
    duplicate_candidates_hint: list[dict[str, object]] = field(default_factory=list)
    extra_role_results: dict[str, dict[str, object]] = field(default_factory=dict)
    triage: TriageResult | None = None
    plan: PlanResult | None = None
    engineering: EngineeringResult | None = None
    diff_report: DiffReport | None = None
    policy_findings: list[str] = field(default_factory=list)


class BaseRole(ABC, Generic[RoleResultT]):
    name: str
    output_model: type[RoleResultT]
    allow_write = False

    def __init__(
        self,
        backend: BackendRunner,
        renderer: PromptRenderer,
        artifact_store: ArtifactStore,
        timeout_seconds: int,
    ) -> None:
        self.backend = backend
        self.renderer = renderer
        self.artifact_store = artifact_store
        self.timeout_seconds = timeout_seconds

    async def run(self, context: PipelineContext) -> tuple[RoleResultT, dict[str, str]]:
        prompt = self.renderer.render(
            role_name=self.name,
            output_model=self.output_model,
            context=self.template_context(context),
        )
        backend_result = await self.backend.run_structured(
            BackendInvocation(
                role_name=self.name,
                prompt=prompt,
                output_model=self.output_model,
                cwd=context.workspace_path,
                timeout_seconds=self.timeout_seconds,
                allow_write=self.allow_write,
                metadata=self.invocation_metadata(context),
            )
        )
        result = backend_result.payload
        markdown = self.render_markdown(result)
        artifacts = self.artifact_store.write_role_artifacts(
            issue_id=context.issue.id,
            run_id=context.run_id,
            role_name=self.name,
            payload=result,
            markdown=markdown,
        )
        if context.loaded.data.agent.debug_artifacts:
            artifacts.update(
                self.artifact_store.write_debug_artifacts(
                    issue_id=context.issue.id,
                    run_id=context.run_id,
                    role_name=self.name,
                    prompt=prompt,
                    raw_output=backend_result.raw_output,
                )
            )
        return result, artifacts

    def template_context(self, context: PipelineContext) -> dict[str, object]:
        review_signals = build_review_signals(context.plan, context.engineering, context.diff_report)
        review_criteria = evaluate_review_criteria(review_signals, context.policy_findings)
        return {
            "issue": context.issue.model_dump(mode="json"),
            "issue_json": json.dumps(context.issue.model_dump(mode="json"), indent=2),
            "issue_comments_excerpt": context.issue.comments_excerpt(),
            "repo_context": context.repo_context,
            "duplicate_candidates_context": context.duplicate_candidates_context,
            "duplicate_candidates_json": json.dumps(context.duplicate_candidates_hint, indent=2),
            "extra_role_results_json": json.dumps(context.extra_role_results, indent=2),
            "triage_result_json": json.dumps(
                context.triage.model_dump(mode="json") if context.triage else {},
                indent=2,
            ),
            "plan_result_json": json.dumps(
                context.plan.model_dump(mode="json") if context.plan else {},
                indent=2,
            ),
            "engineering_result_json": json.dumps(
                context.engineering.model_dump(mode="json") if context.engineering else {},
                indent=2,
            ),
            "diff_report_json": json.dumps(
                context.diff_report.model_dump(mode="json") if context.diff_report else {},
                indent=2,
            ),
            "review_signals_json": json.dumps(
                review_signals.model_dump(mode="json"),
                indent=2,
            ),
            "review_criteria_json": json.dumps(
                review_criteria.to_dict(),
                indent=2,
            ),
            "policy_findings_json": json.dumps(context.policy_findings, indent=2),
            "dry_run": context.dry_run,
        }

    def invocation_metadata(self, context: PipelineContext) -> dict[str, object]:
        review_signals = build_review_signals(context.plan, context.engineering, context.diff_report)
        review_criteria = evaluate_review_criteria(review_signals, context.policy_findings)
        return {
            "issue": context.issue.model_dump(mode="json"),
            "repo_context": context.repo_context,
            "duplicate_candidates_hint": context.duplicate_candidates_hint,
            "extra_role_results": context.extra_role_results,
            "triage": context.triage.model_dump(mode="json") if context.triage else {},
            "plan": context.plan.model_dump(mode="json") if context.plan else {},
            "engineering": context.engineering.model_dump(mode="json") if context.engineering else {},
            "diff_report": context.diff_report.model_dump(mode="json") if context.diff_report else {},
            "review_signals": review_signals.model_dump(mode="json"),
            "review_criteria": review_criteria.to_dict(),
            "policy_findings": context.policy_findings,
            "dry_run": context.dry_run,
        }

    def render_markdown(self, payload: RoleResultT) -> str:
        lines = [f"# {self.name.title()} Result", ""]
        for key, value in payload.model_dump(mode="json").items():
            if isinstance(value, list):
                lines.append(f"## {key}")
                if value:
                    lines.extend(f"- {item}" for item in value)
                else:
                    lines.append("- none")
            else:
                lines.append(f"- **{key}**: {value}")
        return "\n".join(lines) + "\n"
