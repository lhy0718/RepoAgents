from __future__ import annotations

import json
from pathlib import Path

from reporepublic.config import load_config
from reporepublic.sync_artifacts import (
    inspect_applied_sync_manifests,
    SyncActionRegistry,
    apply_sync_artifact,
    apply_sync_bundle,
    list_sync_artifacts,
    summarize_sync_applied_retention,
    resolve_sync_artifact,
    resolve_sync_bundle,
    repair_applied_sync_manifests,
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


def test_inspect_applied_sync_manifest_detects_integrity_issues(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    issue_root = loaded.sync_applied_dir / "local-file" / "issue-1"
    issue_root.mkdir(parents=True, exist_ok=True)
    comment_path = issue_root / "20260308T010101000001Z-comment.md"
    branch_path = issue_root / "20260308T010102000001Z-branch.json"
    orphan_path = issue_root / "20260308T010103000001Z-pr-body.md"
    comment_path.write_text("---\nissue_id: 1\n---\n\nComment handoff.\n", encoding="utf-8")
    branch_path.write_text('{"action":"branch","issue_id":1}\n', encoding="utf-8")
    orphan_path.write_text("---\nissue_id: 1\n---\n\nOrphan handoff.\n", encoding="utf-8")
    (issue_root / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "entry_key": "local-file:local-file/issue-1/20260308T010101000001Z-comment.md",
                    "tracker": "local-file",
                    "issue_id": 1,
                    "action": "comment",
                    "format": "markdown",
                    "applied_at": "2026-03-08T01:01:01+00:00",
                    "staged_at": "20260308T010101000001Z",
                    "summary": "comment handoff",
                    "normalized": {
                        "artifact_role": "comment-proposal",
                        "issue_key": "issue:1",
                        "bundle_key": "issue:1|comment",
                        "refs": {},
                        "links": {"self": "local-file/issue-1/20260308T010101000001Z-comment.md"},
                    },
                    "source_relative_path": "local-file/issue-1/20260308T010101000001Z-comment.md",
                    "archived_relative_path": "local-file/issue-1/20260308T010101000001Z-comment.md",
                    "archived_path": "/tmp/incorrect-comment.md",
                    "effect": "Archived comment handoff.",
                    "handoff": {
                        "group_key": "issue:1|comment",
                        "group_size": 9,
                        "group_index": 5,
                        "group_actions": ["comment", "branch"],
                        "related_entry_keys": ["mismatch"],
                        "related_source_paths": ["mismatch"],
                    },
                },
                {
                    "entry_key": "duplicate-entry",
                    "tracker": "local-file",
                    "issue_id": 1,
                    "action": "branch",
                    "format": "json",
                    "applied_at": "2026-03-08T01:01:02+00:00",
                    "staged_at": "20260308T010102000001Z",
                    "summary": "branch handoff",
                    "normalized": {
                        "artifact_role": "branch-proposal",
                        "issue_key": "issue:1",
                        "bundle_key": "issue:1|head:reporepublic/issue-1-fix",
                        "refs": {"head": "reporepublic/issue-1-fix"},
                        "links": {"self": "local-file/issue-1/20260308T010102000001Z-branch.json"},
                    },
                    "source_relative_path": "local-file/issue-1/20260308T010102000001Z-branch.json",
                    "archived_relative_path": "local-file/issue-1/20260308T010102000001Z-branch.json",
                    "archived_path": str(branch_path),
                    "effect": "Archived branch handoff.",
                    "handoff": {
                        "group_key": "issue:1|head:reporepublic/issue-1-fix",
                        "group_size": 1,
                        "group_index": 0,
                        "group_actions": ["branch"],
                        "related_entry_keys": ["duplicate-entry"],
                        "related_source_paths": ["local-file/issue-1/20260308T010102000001Z-branch.json"],
                    },
                },
                {
                    "entry_key": "duplicate-entry",
                    "tracker": "local-file",
                    "issue_id": 1,
                    "action": "pr-body",
                    "format": "markdown",
                    "applied_at": "2026-03-08T01:01:03+00:00",
                    "staged_at": "20260308T010103000001Z",
                    "summary": "missing archive",
                    "normalized": {
                        "artifact_role": "pr-body-proposal",
                        "issue_key": "issue:1",
                        "bundle_key": "issue:1|head:reporepublic/issue-1-fix",
                        "refs": {"head": "reporepublic/issue-1-fix"},
                        "links": {"self": "local-file/issue-1/20260308T010104000001Z-missing.md"},
                    },
                    "source_relative_path": "local-file/issue-1/20260308T010104000001Z-missing.md",
                    "archived_relative_path": "local-file/issue-1/20260308T010104000001Z-missing.md",
                    "archived_path": str(issue_root / "20260308T010104000001Z-missing.md"),
                    "effect": "Archived missing handoff.",
                    "handoff": {
                        "group_key": "issue:1|head:reporepublic/issue-1-fix",
                        "group_size": 2,
                        "group_index": 1,
                        "group_actions": ["branch", "pr-body"],
                        "related_entry_keys": ["duplicate-entry", "duplicate-entry"],
                        "related_source_paths": [
                            "local-file/issue-1/20260308T010102000001Z-branch.json",
                            "local-file/issue-1/20260308T010104000001Z-missing.md",
                        ],
                    },
                },
            ],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    reports = inspect_applied_sync_manifests(loaded, issue_id=1, tracker="local-file")

    assert len(reports) == 1
    codes = {finding.code for finding in reports[0].findings}
    assert "mismatched_archived_path" in codes
    assert "duplicate_entry_key" in codes
    assert "dangling_archive_reference" in codes
    assert "orphan_archive_file" in codes
    assert "handoff_group_mismatch" in codes


def test_repair_applied_sync_manifest_recovers_orphans_and_rebuilds_group_linkage(demo_repo: Path) -> None:
    loaded = load_config(demo_repo)
    issue_root = loaded.sync_applied_dir / "local-markdown" / "issue-1"
    issue_root.mkdir(parents=True, exist_ok=True)
    branch_path = issue_root / "20260308T010201000001Z-branch.json"
    pr_path = issue_root / "20260308T010202000001Z-pr.json"
    pr_body_path = issue_root / "20260308T010203000001Z-pr-body.md"
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
    pr_body_path.write_text(
        "---\n"
        "issue_id: 1\n"
        'title: "RepoRepublic: Fix empty input crash (#1)"\n'
        "head_branch: reporepublic/issue-1-fix-empty-input\n"
        "base_branch: main\n"
        "staged_at: 20260308T010203000001Z\n"
        "---\n\n"
        "Draft PR proposal staged locally.\n",
        encoding="utf-8",
    )
    (issue_root / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "entry_key": "broken-branch",
                    "tracker": "local-markdown",
                    "issue_id": 1,
                    "action": "branch",
                    "format": "json",
                    "applied_at": "2026-03-08T01:02:01+00:00",
                    "staged_at": "20260308T010201000001Z",
                    "summary": "branch handoff",
                    "normalized": {
                        "artifact_role": "branch-proposal",
                        "issue_key": "issue:1",
                        "bundle_key": "issue:1|head:reporepublic/issue-1-fix-empty-input",
                        "refs": {"head": "reporepublic/issue-1-fix-empty-input"},
                        "links": {"self": "local-markdown/issue-1/20260308T010201000001Z-branch.json"},
                    },
                    "source_relative_path": "local-markdown/issue-1/20260308T010201000001Z-branch.json",
                    "archived_relative_path": "local-markdown/issue-1/20260308T010201000001Z-branch.json",
                    "archived_path": "/tmp/broken-branch.json",
                    "effect": "Archived branch handoff.",
                    "handoff": {
                        "group_key": "issue:1|head:reporepublic/issue-1-fix-empty-input",
                        "group_size": 1,
                        "group_index": 0,
                        "group_actions": ["branch"],
                        "related_entry_keys": ["broken-branch"],
                        "related_source_paths": ["local-markdown/issue-1/20260308T010201000001Z-branch.json"],
                    },
                }
            ],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    preview = repair_applied_sync_manifests(loaded, issue_id=1, tracker="local-markdown", dry_run=True)
    applied = repair_applied_sync_manifests(loaded, issue_id=1, tracker="local-markdown", dry_run=False)
    repaired_payload = json.loads((issue_root / "manifest.json").read_text(encoding="utf-8"))

    assert len(preview) == 1
    assert preview[0].changed is True
    assert preview[0].adopted_archives == 2
    assert preview[0].findings_after == 0
    assert len(applied) == 1
    assert applied[0].changed is True
    assert applied[0].manifest_entry_count_after == 3
    assert applied[0].findings_after == 0
    assert [entry["action"] for entry in repaired_payload] == ["branch", "pr", "pr-body"]
    assert repaired_payload[0]["archived_path"] == str(branch_path.resolve())
    assert repaired_payload[0]["handoff"]["group_size"] == 3
    assert repaired_payload[0]["handoff"]["group_actions"] == ["branch", "pr", "pr-body"]
    assert repaired_payload[1]["handoff"]["group_index"] == 1
    assert repaired_payload[2]["handoff"]["group_index"] == 2
    assert repaired_payload[2]["normalized"]["links"]["self"] == "local-markdown/issue-1/20260308T010203000001Z-pr-body.md"


def test_summarize_sync_applied_retention_reports_prunable_groups(demo_repo: Path) -> None:
    config_path = demo_repo / ".ai-republic" / "reporepublic.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "sync_applied_keep_groups_per_issue: 20",
            "sync_applied_keep_groups_per_issue: 1",
        ),
        encoding="utf-8",
    )
    loaded = load_config(demo_repo)
    issue_root = loaded.sync_applied_dir / "local-markdown" / "issue-1"
    issue_root.mkdir(parents=True, exist_ok=True)
    older_branch = issue_root / "20260308T010001000001Z-branch.json"
    newer_comment = issue_root / "20260308T010101000001Z-comment.md"
    older_branch.write_text(
        json.dumps(
            {
                "action": "branch",
                "issue_id": 1,
                "branch_name": "reporepublic/issue-1-older",
                "staged_at": "20260308T010001000001Z",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    newer_comment.write_text("---\nissue_id: 1\n---\n\nRecent comment.\n", encoding="utf-8")
    (issue_root / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "entry_key": "local-markdown:local-markdown/issue-1/20260308T010001000001Z-branch.json",
                    "tracker": "local-markdown",
                    "issue_id": 1,
                    "action": "branch",
                    "format": "json",
                    "applied_at": "2026-03-08T01:00:01+00:00",
                    "staged_at": "20260308T010001000001Z",
                    "summary": "Older branch handoff.",
                    "normalized": {
                        "artifact_role": "branch-proposal",
                        "issue_key": "issue:1",
                        "bundle_key": "issue:1|head:reporepublic/issue-1-older",
                        "refs": {"head": "reporepublic/issue-1-older"},
                        "links": {"self": "local-markdown/issue-1/20260308T010001000001Z-branch.json"},
                    },
                    "source_relative_path": "local-markdown/issue-1/20260308T010001000001Z-branch.json",
                    "archived_relative_path": "local-markdown/issue-1/20260308T010001000001Z-branch.json",
                    "archived_path": str(older_branch),
                    "effect": "Archived branch handoff.",
                    "handoff": {
                        "group_key": "issue:1|head:reporepublic/issue-1-older",
                        "group_size": 1,
                        "group_index": 0,
                        "group_actions": ["branch"],
                        "related_entry_keys": [
                            "local-markdown:local-markdown/issue-1/20260308T010001000001Z-branch.json"
                        ],
                        "related_source_paths": [
                            "local-markdown/issue-1/20260308T010001000001Z-branch.json"
                        ],
                    },
                },
                {
                    "entry_key": "local-markdown:local-markdown/issue-1/20260308T010101000001Z-comment.md",
                    "tracker": "local-markdown",
                    "issue_id": 1,
                    "action": "comment",
                    "format": "markdown",
                    "applied_at": "2026-03-08T01:01:01+00:00",
                    "staged_at": "20260308T010101000001Z",
                    "summary": "Recent comment handoff.",
                    "normalized": {
                        "artifact_role": "comment-proposal",
                        "issue_key": "issue:1",
                        "bundle_key": "issue:1|comment",
                        "refs": {},
                        "links": {"self": "local-markdown/issue-1/20260308T010101000001Z-comment.md"},
                    },
                    "source_relative_path": "local-markdown/issue-1/20260308T010101000001Z-comment.md",
                    "archived_relative_path": "local-markdown/issue-1/20260308T010101000001Z-comment.md",
                    "archived_path": str(newer_comment),
                    "effect": "Archived comment handoff.",
                    "handoff": {
                        "group_key": "issue:1|comment",
                        "group_size": 1,
                        "group_index": 0,
                        "group_actions": ["comment"],
                        "related_entry_keys": [
                            "local-markdown:local-markdown/issue-1/20260308T010101000001Z-comment.md"
                        ],
                        "related_source_paths": [
                            "local-markdown/issue-1/20260308T010101000001Z-comment.md"
                        ],
                    },
                },
            ],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    snapshot = summarize_sync_applied_retention(loaded, limit=10)

    assert snapshot.keep_groups_per_issue == 1
    assert snapshot.total_issues == 1
    assert snapshot.prunable_issues == 1
    assert snapshot.prunable_groups == 1
    assert snapshot.entries[0].status == "prunable"
    assert snapshot.entries[0].groups[0].status == "kept"
    assert snapshot.entries[0].groups[1].status == "prunable"
    assert snapshot.entries[0].prunable_bytes > 0
