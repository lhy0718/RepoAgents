from __future__ import annotations

import json
from pathlib import Path

from reporepublic.config import load_config
from reporepublic.sync_artifacts import (
    SyncActionRegistry,
    apply_sync_artifact,
    apply_sync_bundle,
    list_sync_artifacts,
    resolve_sync_artifact,
    resolve_sync_bundle,
)


def test_sync_artifact_inventory_parses_markdown_and_json(demo_repo: Path) -> None:
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-markdown" / "issue-1"
    sync_dir.mkdir(parents=True, exist_ok=True)
    (sync_dir / "20260308T010101000001Z-comment.md").write_text(
        "---\n"
        "issue_id: 1\n"
        "action: post_comment\n"
        "staged_at: 20260308T010101000001Z\n"
        "---\n\n"
        "RepoRepublic staged a maintainer note.\n",
        encoding="utf-8",
    )
    (sync_dir / "20260308T010102000001Z-branch.json").write_text(
        '{\n  "action": "branch",\n  "branch_name": "reporepublic/issue-1-fix",\n  "staged_at": "20260308T010102000001Z"\n}\n',
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    artifacts = list_sync_artifacts(loaded)

    assert len(artifacts) == 2
    assert artifacts[0].action == "branch"
    assert artifacts[0].summary == "branch=reporepublic/issue-1-fix"
    assert artifacts[1].action == "comment"
    assert artifacts[1].format == "markdown"
    assert artifacts[1].summary == "RepoRepublic staged a maintainer note."


def test_sync_artifact_inventory_filters_and_resolves_by_relative_path(demo_repo: Path) -> None:
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-markdown" / "issue-2"
    sync_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = sync_dir / "20260308T010103000001Z-pr-body.md"
    artifact_path.write_text(
        "---\n"
        "issue_id: 2\n"
        'title: "RepoRepublic: Improve README quickstart (#2)"\n'
        "staged_at: 20260308T010103000001Z\n"
        "---\n\n"
        "Draft PR proposal staged locally.\n",
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    filtered = list_sync_artifacts(loaded, issue_id=2, tracker="local_markdown", action="pr_body")
    resolved = resolve_sync_artifact(loaded, "local-markdown/issue-2/20260308T010103000001Z-pr-body.md")

    assert len(filtered) == 1
    assert filtered[0].relative_path == "local-markdown/issue-2/20260308T010103000001Z-pr-body.md"
    assert filtered[0].normalized["artifact_role"] == "pr-body-proposal"
    assert filtered[0].normalized["issue_key"] == "issue:2"
    assert resolved.path == artifact_path.resolve()
    assert resolved.action == "pr-body"


def test_sync_apply_moves_comment_to_applied_archive_and_updates_issue_file(demo_repo: Path) -> None:
    issue_dir = demo_repo / "issues"
    issue_dir.mkdir(exist_ok=True)
    issue_path = issue_dir / "001-demo.md"
    issue_path.write_text(
        "---\n"
        "id: 1\n"
        "title: Fix empty input crash\n"
        "labels:\n"
        "  - bug\n"
        "---\n\n"
        "Return an empty list.\n",
        encoding="utf-8",
    )
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("kind: github", "kind: local_markdown")
        .replace("repo: demo/repo\n", "path: issues\n")
        .replace("mode: fixture\n", ""),
        encoding="utf-8",
    )
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-markdown" / "issue-1"
    sync_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = sync_dir / "20260308T010104000001Z-comment.md"
    artifact_path.write_text(
        "---\n"
        "issue_id: 1\n"
        "action: post_comment\n"
        "staged_at: 20260308T010104000001Z\n"
        "---\n\n"
        "RepoRepublic staged a maintainer note.\n",
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    artifact = resolve_sync_artifact(loaded, "local-markdown/issue-1/20260308T010104000001Z-comment.md")
    result = apply_sync_artifact(loaded, artifact)

    manifest_payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    issue_body = issue_path.read_text(encoding="utf-8")
    assert not artifact_path.exists()
    assert result.archived_path.exists()
    assert "RepoRepublic staged a maintainer note." in issue_body
    assert "reporepublic" in issue_body
    assert manifest_payload[-1]["action"] == "comment"
    assert manifest_payload[-1]["entry_key"] == "local-markdown:local-markdown/issue-1/20260308T010104000001Z-comment.md"
    assert manifest_payload[-1]["archived_relative_path"] == "local-markdown/issue-1/20260308T010104000001Z-comment.md"
    assert manifest_payload[-1]["handoff"]["group_size"] == 1
    assert manifest_payload[-1]["handoff"]["related_source_paths"] == [
        "local-markdown/issue-1/20260308T010104000001Z-comment.md"
    ]
    assert manifest_payload[-1]["normalized"]["artifact_role"] == "comment-proposal"
    assert manifest_payload[-1]["effect"].startswith("Appended staged comment")


def test_sync_apply_updates_local_file_issue_json_and_archives_artifact(demo_repo: Path) -> None:
    issue_path = demo_repo / "issues.json"
    issue_path.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "id": 1,
                        "number": 1,
                        "title": "Fix empty input crash",
                        "body": "Return an empty list.",
                        "labels": ["bug"],
                        "comments": [],
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("kind: github", "kind: local_file")
        .replace("repo: demo/repo\n", "path: issues.json\n")
        .replace("mode: fixture\n", ""),
        encoding="utf-8",
    )
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-file" / "issue-1"
    sync_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = sync_dir / "20260308T010105000001Z-labels.json"
    artifact_path.write_text(
        json.dumps(
            {
                "action": "labels",
                "issue_id": 1,
                "labels": ["bug", "accepted"],
                "staged_at": "20260308T010105000001Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    artifact = resolve_sync_artifact(loaded, "local-file/issue-1/20260308T010105000001Z-labels.json")
    result = apply_sync_artifact(loaded, artifact)
    reloaded = json.loads(issue_path.read_text(encoding="utf-8"))

    assert not artifact_path.exists()
    assert result.archived_path.exists()
    assert reloaded["issues"][0]["labels"] == ["bug", "accepted"]


def test_sync_bundle_resolves_and_archives_related_local_file_pr_handoff(demo_repo: Path) -> None:
    issue_path = demo_repo / "issues.json"
    issue_path.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "id": 1,
                        "number": 1,
                        "title": "Fix empty input crash",
                        "body": "Return an empty list.",
                        "labels": ["bug"],
                        "comments": [],
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("kind: github", "kind: local_file")
        .replace("repo: demo/repo\n", "path: issues.json\n")
        .replace("mode: fixture\n", ""),
        encoding="utf-8",
    )
    sync_dir = demo_repo / ".ai-republic" / "sync" / "local-file" / "issue-1"
    sync_dir.mkdir(parents=True, exist_ok=True)
    branch_path = sync_dir / "20260308T010201000001Z-branch.json"
    branch_path.write_text(
        json.dumps(
            {
                "action": "branch",
                "issue_id": 1,
                "branch_name": "reporepublic/issue-1-fix-empty-input",
                "base_branch": "main",
                "staged_at": "20260308T010201000001Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    pr_path = sync_dir / "20260308T010202000001Z-pr.json"
    pr_path.write_text(
        json.dumps(
            {
                "action": "pr",
                "issue_id": 1,
                "title": "RepoRepublic: Fix empty input crash (#1)",
                "head_branch": "reporepublic/issue-1-fix-empty-input",
                "base_branch": "main",
                "draft": True,
                "staged_at": "20260308T010202000001Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    pr_body_path = sync_dir / "20260308T010203000001Z-pr-body.md"
    pr_body_path.write_text(
        "---\n"
        "issue_id: 1\n"
        'title: "RepoRepublic: Fix empty input crash (#1)"\n'
        "head_branch: reporepublic/issue-1-fix-empty-input\n"
        "base_branch: main\n"
        f"metadata_path: {pr_path.resolve()}\n"
        "staged_at: 20260308T010203000001Z\n"
        "---\n\n"
        "Draft PR proposal staged locally.\n",
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    selected = resolve_sync_artifact(loaded, "local-file/issue-1/20260308T010203000001Z-pr-body.md")
    bundle = resolve_sync_bundle(loaded, selected)
    results = apply_sync_bundle(loaded, selected)
    manifest_payload = json.loads(results[-1].manifest_path.read_text(encoding="utf-8"))

    assert [artifact.action for artifact in bundle] == ["branch", "pr", "pr-body"]
    assert bundle[0].normalized["bundle_key"] == "issue:1|head:reporepublic/issue-1-fix-empty-input"
    assert bundle[1].normalized["refs"]["head"] == "reporepublic/issue-1-fix-empty-input"
    assert bundle[2].normalized["links"]["metadata_artifact"] == "local-file/issue-1/20260308T010202000001Z-pr.json"
    assert [result.action for result in results] == ["branch", "pr", "pr-body"]
    assert not branch_path.exists()
    assert not pr_path.exists()
    assert not pr_body_path.exists()
    assert len(manifest_payload) == 3
    assert [entry["action"] for entry in manifest_payload] == ["branch", "pr", "pr-body"]
    assert manifest_payload[0]["handoff"]["group_size"] == 3
    assert manifest_payload[0]["handoff"]["group_actions"] == ["branch", "pr", "pr-body"]
    assert manifest_payload[0]["handoff"]["group_index"] == 0
    assert manifest_payload[1]["handoff"]["group_index"] == 1
    assert manifest_payload[2]["handoff"]["group_index"] == 2
    assert manifest_payload[0]["handoff"]["related_entry_keys"] == [
        "local-file:local-file/issue-1/20260308T010201000001Z-branch.json",
        "local-file:local-file/issue-1/20260308T010202000001Z-pr.json",
        "local-file:local-file/issue-1/20260308T010203000001Z-pr-body.md",
    ]
    assert manifest_payload[2]["archived_relative_path"] == "local-file/issue-1/20260308T010203000001Z-pr-body.md"


def test_sync_registry_supports_custom_apply_handler(demo_repo: Path) -> None:
    sync_dir = demo_repo / ".ai-republic" / "sync" / "custom-tracker" / "issue-7"
    sync_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = sync_dir / "20260308T010301000001Z-export.json"
    artifact_path.write_text(
        json.dumps(
            {
                "action": "export",
                "issue_id": 7,
                "staged_at": "20260308T010301000001Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    artifact = resolve_sync_artifact(loaded, "custom-tracker/issue-7/20260308T010301000001Z-export.json")
    registry = SyncActionRegistry()
    registry.register_apply_handler("custom-tracker", "export", lambda _loaded, _artifact: "Custom export applied.")

    result = apply_sync_artifact(loaded, artifact, registry=registry)
    manifest_payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert result.effect == "Custom export applied."
    assert result.archived_path.exists()
    assert manifest_payload[-1]["normalized"]["artifact_role"] == "export-proposal"
    assert manifest_payload[-1]["effect"] == "Custom export applied."


def test_sync_registry_supports_custom_bundle_resolver(demo_repo: Path) -> None:
    sync_dir = demo_repo / ".ai-republic" / "sync" / "custom-tracker" / "issue-9"
    sync_dir.mkdir(parents=True, exist_ok=True)
    branch_path = sync_dir / "20260308T010401000001Z-branch.json"
    branch_path.write_text(
        json.dumps(
            {
                "action": "branch",
                "issue_id": 9,
                "branch_name": "custom/issue-9",
                "staged_at": "20260308T010401000001Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    pr_body_path = sync_dir / "20260308T010402000001Z-pr-body.md"
    pr_body_path.write_text(
        "---\n"
        "issue_id: 9\n"
        "head_branch: custom/issue-9\n"
        "staged_at: 20260308T010402000001Z\n"
        "---\n\n"
        "Custom tracker handoff.\n",
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    branch_artifact = resolve_sync_artifact(loaded, "custom-tracker/issue-9/20260308T010401000001Z-branch.json")
    pr_body_artifact = resolve_sync_artifact(loaded, "custom-tracker/issue-9/20260308T010402000001Z-pr-body.md")
    registry = SyncActionRegistry()
    registry.register_apply_handler("custom-tracker", "*", lambda _loaded, artifact: f"Handled {artifact.action}.")
    registry.register_bundle_resolver(
        "custom-tracker",
        lambda _loaded, artifact: [artifact, pr_body_artifact] if artifact.action == "branch" else [artifact],
    )

    bundle = resolve_sync_bundle(loaded, branch_artifact, registry=registry)
    results = apply_sync_bundle(loaded, branch_artifact, registry=registry)

    assert [artifact.action for artifact in bundle] == ["branch", "pr-body"]
    assert [result.action for result in results] == ["branch", "pr-body"]
    assert all(result.archived_path.exists() for result in results)
