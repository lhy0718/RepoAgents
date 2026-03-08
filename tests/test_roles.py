from __future__ import annotations

import asyncio
from pathlib import Path

from reporepublic.backend.mock import MockBackend
from reporepublic.config import load_config
from reporepublic.models import IssueRef, QAResult, RoleName, TriageResult
from reporepublic.prompts import PromptRenderer
from reporepublic.roles import PipelineContext, TriageRole, build_role_sequence
from reporepublic.utils import ArtifactStore, build_repo_context


def test_role_result_schema_and_artifacts(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    backend = MockBackend()
    renderer = PromptRenderer(loaded)
    artifacts = ArtifactStore(loaded.artifacts_dir)
    role = TriageRole(backend, renderer, artifacts, timeout_seconds=30)
    issue = IssueRef(id=1, title="Fix empty input crash", body="Empty input should return [].")
    workspace = demo_repo
    context = PipelineContext(
        loaded=loaded,
        issue=issue,
        workspace_path=workspace,
        run_id="run-1",
        dry_run=False,
        repo_context=build_repo_context(workspace),
    )
    result, paths = asyncio.run(role.run(context))
    assert isinstance(result, TriageResult)
    assert result.issue_type.value == "bug"
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()


def test_role_debug_artifacts_include_prompt_and_raw_output(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    loaded.data.agent.debug_artifacts = True
    backend = MockBackend()
    renderer = PromptRenderer(loaded)
    artifacts = ArtifactStore(loaded.artifacts_dir)
    role = TriageRole(backend, renderer, artifacts, timeout_seconds=30)
    issue = IssueRef(id=1, title="Fix empty input crash", body="Empty input should return [].")
    context = PipelineContext(
        loaded=loaded,
        issue=issue,
        workspace_path=demo_repo,
        run_id="run-debug",
        dry_run=False,
        repo_context=build_repo_context(demo_repo),
    )

    _, paths = asyncio.run(role.run(context))

    assert Path(paths["prompt"]).exists()
    assert Path(paths["raw_output"]).exists()
    assert "RepoRepublic's `triage` role" in Path(paths["prompt"]).read_text(encoding="utf-8")
    assert '"issue_type"' in Path(paths["raw_output"]).read_text(encoding="utf-8")


def test_role_registry_builds_optional_qa_role(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    backend = MockBackend()
    renderer = PromptRenderer(loaded)
    artifacts = ArtifactStore(loaded.artifacts_dir)

    roles = build_role_sequence(
        [RoleName.TRIAGE, RoleName.PLANNER, RoleName.ENGINEER, RoleName.QA, RoleName.REVIEWER],
        backend=backend,
        renderer=renderer,
        artifacts=artifacts,
        timeout_seconds=30,
    )

    assert [role.name for role in roles] == ["triage", "planner", "engineer", "qa", "reviewer"]
    assert roles[3].output_model is QAResult
