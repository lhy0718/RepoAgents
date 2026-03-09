from __future__ import annotations

import json
from pathlib import Path

from reporepublic.config import load_config
from reporepublic.sync_manifest_reports import (
    build_sync_check_report,
    build_sync_repair_report,
)


def test_build_sync_check_report_writes_outputs_and_finding_summary(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    applied_root = demo_repo / ".ai-republic" / "sync-applied" / "local-file" / "issue-1"
    applied_root.mkdir(parents=True, exist_ok=True)
    (applied_root / "20260308T010105000001Z-comment.md").write_text(
        "---\nissue_id: 1\n---\n\nOrphan handoff.\n",
        encoding="utf-8",
    )

    loaded = load_config(demo_repo)
    output_path = demo_repo / "tmp" / "sync-check.json"
    result = build_sync_check_report(
        loaded,
        output_path=output_path,
        formats=("json", "markdown"),
        issue_id=1,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    markdown = output_path.with_suffix(".md").read_text(encoding="utf-8")

    assert result.overall_status == "issues"
    assert result.total_reports == 1
    assert result.issues_with_findings == 1
    assert result.total_findings == 2
    assert payload["summary"]["finding_counts"]["missing_manifest"] == 1
    assert payload["summary"]["finding_counts"]["orphan_archive_file"] == 1
    assert payload["reports"][0]["status"] == "issues"
    assert "orphan_archive_file" in markdown


def test_build_sync_repair_report_preview_writes_outputs_and_adoption_counts(
    demo_repo: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(demo_repo)
    applied_root = demo_repo / ".ai-republic" / "sync-applied" / "local-markdown" / "issue-1"
    applied_root.mkdir(parents=True, exist_ok=True)
    branch_path = applied_root / "20260308T010201000001Z-branch.json"
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

    loaded = load_config(demo_repo)
    output_path = demo_repo / "tmp" / "sync-repair-preview.json"
    result = build_sync_repair_report(
        loaded,
        dry_run=True,
        output_path=output_path,
        formats=("json", "markdown"),
        issue_id=1,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    markdown = output_path.with_suffix(".md").read_text(encoding="utf-8")

    assert result.overall_status == "preview"
    assert result.total_reports == 1
    assert result.changed_reports == 1
    assert result.findings_before == 2
    assert result.findings_after == 0
    assert result.adopted_archives == 1
    assert not (applied_root / "manifest.json").exists()
    assert payload["results"][0]["status"] == "changed"
    assert payload["results"][0]["adopted_archives"] == 1
    assert "adopted_archives: 1" in markdown
