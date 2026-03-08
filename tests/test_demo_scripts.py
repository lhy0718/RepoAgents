from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from reporepublic.config import load_config


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_demo_python_lib_script_runs_in_temp_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "python-lib-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_python_lib.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".ai-republic" / "state" / "runs.json").exists()
    assert (dest / ".ai-republic" / "artifacts").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()


def test_demo_web_app_script_runs_in_temp_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "web-app-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_web_app.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".ai-republic" / "state" / "runs.json").exists()
    assert (dest / ".ai-republic" / "artifacts").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()


def test_demo_local_file_tracker_script_runs_in_temp_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "local-file-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_local_file_tracker.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".ai-republic" / "state" / "runs.json").exists()
    assert (dest / ".ai-republic" / "artifacts").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()


def test_demo_local_markdown_tracker_script_runs_in_temp_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "local-markdown-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_local_markdown_tracker.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".ai-republic" / "state" / "runs.json").exists()
    assert (dest / ".ai-republic" / "artifacts").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()


def test_demo_local_markdown_sync_script_runs_in_temp_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "local-markdown-sync-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_local_markdown_sync.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
        },
    )

    sync_dir = dest / ".ai-republic" / "sync" / "local-markdown" / "issue-1"
    applied_dir = dest / ".ai-republic" / "sync-applied" / "local-markdown" / "issue-1"
    manifest_payload = json.loads((applied_dir / "manifest.json").read_text(encoding="utf-8")) if (applied_dir / "manifest.json").exists() else []
    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".ai-republic" / "state" / "runs.json").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()
    assert sync_dir.exists()
    assert not list(sync_dir.glob("*-pr-body.md"))
    assert applied_dir.exists()
    assert list(applied_dir.glob("*-comment.md"))
    assert list(applied_dir.glob("*-branch.json"))
    assert list(applied_dir.glob("*-pr.json"))
    assert list(applied_dir.glob("*-pr-body.md"))
    assert (applied_dir / "manifest.json").exists()
    assert any(entry["handoff"]["group_size"] == 3 for entry in manifest_payload if entry["action"] == "pr-body")
    assert "Applied sync artifact:" in completed.stdout
    assert "Applied sync bundle:" in completed.stdout


def test_demo_local_file_sync_script_runs_in_temp_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "local-file-sync-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_local_file_sync.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
        },
    )

    sync_dir = dest / ".ai-republic" / "sync" / "local-file" / "issue-1"
    applied_dir = dest / ".ai-republic" / "sync-applied" / "local-file" / "issue-1"
    issue_payload = load_config(dest).resolve(Path("issues.json"))
    issue_data = json.loads(issue_payload.read_text(encoding="utf-8"))
    manifest_payload = json.loads((applied_dir / "manifest.json").read_text(encoding="utf-8")) if (applied_dir / "manifest.json").exists() else []
    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".ai-republic" / "state" / "runs.json").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()
    assert sync_dir.exists()
    assert applied_dir.exists()
    assert list(applied_dir.glob("*-comment.md"))
    assert (applied_dir / "manifest.json").exists()
    assert manifest_payload[-1]["handoff"]["group_size"] == 1
    assert issue_data[0]["comments"][-1]["author"] == "reporepublic"
    assert "Applied sync artifact:" in completed.stdout


def test_demo_qa_role_pack_script_runs_in_temp_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "qa-role-pack-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_qa_role_pack.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".ai-republic" / "state" / "runs.json").exists()
    assert (dest / ".ai-republic" / "artifacts").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()
    assert list((dest / ".ai-republic" / "artifacts").glob("issue-1/*/qa.json"))
    assert list((dest / ".ai-republic" / "artifacts").glob("issue-1/*/qa.md"))


def test_demo_docs_maintainer_pack_script_runs_in_temp_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "docs-maintainer-pack-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_docs_maintainer_pack.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".ai-republic" / "state" / "runs.json").exists()
    assert (dest / ".ai-republic" / "artifacts").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()
    assert (dest / ".ai-republic" / "prompts" / "planner.txt.j2").exists()
    assert (dest / ".ai-republic" / "policies" / "scope-policy.md").read_text(encoding="utf-8").startswith(
        "# Scope Policy\n\nPack: `docs-maintainer-pack`"
    )
    assert "## Docs Maintainer Pack" in (dest / "AGENTS.md").read_text(encoding="utf-8")
    assert list((dest / ".ai-republic" / "artifacts").glob("issue-1/*/planner.md"))


def test_demo_webhook_receiver_script_runs_in_temp_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "webhook-receiver-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_webhook_receiver.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
            "REPOREPUBLIC_WEBHOOK_PORT": "8791",
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".ai-republic" / "state" / "runs.json").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()
    assert list((dest / ".ai-republic" / "inbox" / "webhooks").glob("*.json"))


def test_demo_webhook_signature_receiver_script_runs_in_temp_workspace(tmp_path: Path) -> None:
    dest = tmp_path / "webhook-signature-receiver-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_webhook_signature_receiver.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
            "REPOREPUBLIC_WEBHOOK_PORT": "8792",
            "REPOREPUBLIC_WEBHOOK_SECRET": "reporepublic-test-secret",
        },
    )

    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".ai-republic" / "state" / "runs.json").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()
    assert list((dest / ".ai-republic" / "inbox" / "webhooks").glob("*.json"))


def test_demo_live_ops_script_prepares_live_blueprint(tmp_path: Path) -> None:
    dest = tmp_path / "live-ops-demo"
    completed = subprocess.run(
        ["bash", "scripts/demo_live_ops.sh"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "REPOREPUBLIC_DEMO_DEST": str(dest),
        },
    )

    loaded = load_config(dest)
    assert completed.returncode == 0, completed.stderr
    assert "Demo workspace:" in completed.stdout
    assert (dest / ".git").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.html").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.json").exists()
    assert (dest / ".ai-republic" / "dashboard" / "index.md").exists()
    assert (dest / ".ai-republic" / "logs").exists()
    assert (dest / "ops" / "republic.env.example").exists()
    assert loaded.data.tracker.kind.value == "github"
    assert loaded.data.tracker.mode.value == "rest"
    assert loaded.data.workspace.strategy == "worktree"
    assert loaded.data.workspace.dirty_policy.value == "block"
    assert loaded.data.logging.file_enabled is True
    assert loaded.data.llm.mode.value == "codex"
