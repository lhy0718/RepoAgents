# Quickstart

## 1. Install dependencies

```bash
uv sync --dev
codex --version
```

If Codex is not logged in yet:

```bash
codex login
```

Optional live smoke test:

```bash
CODEX_E2E=1 uv run pytest tests/test_codex_backend.py -k live_smoke -rs
GITHUB_E2E=1 REPOREPUBLIC_GITHUB_TEST_REPO=owner/name uv run pytest tests/test_tracker.py -k live_read_only -rs
REPOREPUBLIC_GITHUB_WRITE_E2E=1 REPOREPUBLIC_GITHUB_WRITE_TEST_REPO=owner/name REPOREPUBLIC_GITHUB_WRITE_TEST_ISSUE=123 uv run pytest tests/test_tracker.py -k live_comment_write -rs
REPOREPUBLIC_GITHUB_PR_E2E=1 REPOREPUBLIC_GITHUB_PR_TEST_REPO=owner/name REPOREPUBLIC_GITHUB_PR_TEST_ISSUE=123 uv run pytest tests/test_tracker.py -k live_draft_pr_publish -rs
```

## 2. Initialize a target repo

```bash
cd /path/to/your/repo
uv run republic init
uv run republic init --preset python-library --tracker-repo owner/name
uv run republic init --tracker-kind local_file --tracker-path issues.json
uv run republic doctor
uv run republic ops snapshot --archive
uv run republic ops snapshot --archive --history-limit 5 --prune-history
uv run republic ops status
cat .ai-republic/reports/ops/latest.json
```

Running `uv run republic init` without flags starts an interactive setup flow. Use `--backend mock` if you want the initialized config to default to the deterministic mock backend. Use `--tracker-kind local_file` when you want a local JSON inbox instead of GitHub.

Generated control files:

- `.ai-republic/reporepublic.yaml`
- `.ai-republic/roles/*`
- `.ai-republic/prompts/*`
- `.ai-republic/policies/*`
- `AGENTS.md`
- `WORKFLOW.md`

To inspect managed template drift later without overwriting local edits:

```bash
uv run republic init --upgrade
uv run republic init --upgrade --force
```

## 3. Run a local deterministic demo

Fast path:

```bash
bash scripts/demo_python_lib.sh
bash scripts/demo_local_file_tracker.sh
bash scripts/demo_live_ops.sh
bash scripts/release_preflight.sh
```

More runnable demos:

<details>
<summary>Full demo matrix</summary>

```bash
bash scripts/demo_web_app.sh
bash scripts/demo_local_file_sync.sh
bash scripts/demo_local_markdown_tracker.sh
bash scripts/demo_local_markdown_sync.sh
bash scripts/demo_qa_role_pack.sh
bash scripts/demo_webhook_receiver.sh
bash scripts/demo_webhook_signature_receiver.sh
bash scripts/demo_live_publish_sandbox.sh
bash scripts/demo_release_rehearsal.sh
bash scripts/demo_release_publish_dry_run.sh
```

</details>

These scripts copy the example repos into temporary workspaces so the checked-in examples stay untouched.

`bash scripts/demo_live_ops.sh` now goes beyond a blueprint-only setup: it rehearses `github smoke`, generates an `ops snapshot` handoff bundle plus archive, refreshes `ops-status`, and leaves the reading order pinned inside `examples/live-github-ops/ops/handoff-order.md`.

`bash scripts/demo_live_publish_sandbox.sh` adds the next rollout layer: it walks `baseline -> comments-ready -> pr-gated -> pr-ready`, records phase reports under `.ai-republic/reports/sandbox-rollout/`, proves that `github smoke --require-write-ready` fails before the branch-policy gate is fixed and passes after, generates the final sandbox readiness bundle under `.ai-republic/reports/ops/sandbox-pr-ready/`, then runs one deterministic issue and leaves an execution bundle under `.ai-republic/reports/ops/sandbox-issue-201/`.

`bash scripts/demo_release_rehearsal.sh` copies the current repository into a disposable workspace, generates `release preview` and `release announce` artifacts, creates a local annotated rehearsal tag, runs `uv build`, and records tag/build evidence under `.ai-republic/reports/release-rehearsal/`.

`bash scripts/demo_release_publish_dry_run.sh` adds the next release step: it patches the disposable workspace to the inferred preview version, creates a local annotated rehearsal tag, runs `republic release assets --build --smoke-install --format all`, and leaves publish-ready checksum and upload-command evidence under `.ai-republic/reports/release-publish-dry-run/`.

When you want the real repository pre-publish gate instead of a disposable demo, run:

```bash
bash scripts/release_preflight.sh
```

That wrapper runs `republic release check --format all`, which executes release preview, announcement copy-pack generation, `uv run pytest -q`, `uv build`, wheel smoke install, and OSS governance/CI checks in one pass.

```bash
cd examples/python-lib
uv run republic init --preset python-library --fixture-issues issues.json --tracker-repo demo/python-lib
python3 - <<'PY'
from pathlib import Path
path = Path(".ai-republic/reporepublic.yaml")
body = path.read_text()
path.write_text(body.replace("mode: codex", "mode: mock"))
PY
uv run republic run --dry-run
uv run republic run --once
uv run republic status
uv run republic dashboard
uv run republic ops snapshot --include-cleanup-preview --include-cleanup-result --include-sync-check --include-sync-repair-preview --archive
uv run republic ops status --format all
cat .ai-republic/reports/ops/history.json
```

`ops snapshot` history retention defaults to `cleanup.ops_snapshot_keep_entries`. Add `--prune-history` only when you want RepoRepublic to delete dropped managed bundle/archive paths under `.ai-republic/reports/ops/`.
Use `ops status` when you want one CLI/export surface that includes the latest indexed handoff bundle, recent history, the current handoff brief headline, landing paths, and the latest bundle's linked `sync-health` / `sync-audit` posture, plus `github-smoke` for live GitHub REST trackers, without opening the dashboard.

What happens:

1. RepoRepublic reads fixture issues through the GitHub tracker adapter in fixture mode.
2. The orchestrator runs `triage` and `planner` in dry-run mode.
3. In `--once` mode it runs the full pipeline, writes artifacts, and persists state.

If you want to stay entirely off GitHub, configure:

```yaml
tracker:
  kind: local_file
  path: issues.json
```

The bundled offline examples for that path are:

```bash
cd examples/local-file-inbox
uv run republic init --preset python-library --tracker-kind local_file --tracker-path issues.json --backend mock
uv run republic trigger 1
uv run republic dashboard
```

```bash
cd examples/local-file-sync
bash ../../scripts/demo_local_file_sync.sh
```

```bash
cd examples/local-markdown-inbox
uv run republic init --preset python-library --tracker-kind local_markdown --tracker-path issues --backend mock
uv run republic trigger 1
uv run republic dashboard
```

```bash
cd examples/local-markdown-sync
bash ../../scripts/demo_local_markdown_sync.sh
```

That path keeps the tracker offline but stages publication proposals under `.ai-republic/sync/local-markdown/issue-1/`.
Use `uv run republic sync ls --issue 1` to inspect the staged inventory and `uv run republic sync show ...` to open one proposal.
Use `uv run republic sync apply --issue 1 --tracker local-markdown --action comment --latest` to append the newest comment proposal to the source Markdown issue and move the handled artifact into `.ai-republic/sync-applied/`.
Use `uv run republic sync apply --issue 1 --tracker local-markdown --action pr-body --latest --bundle` to archive the related branch/PR handoff set in one step.
The equivalent JSON-inbox flow is `uv run republic sync apply --issue 1 --tracker local-file --action comment --latest`.
Use `uv run republic sync check --issue 1` to inspect applied manifest integrity, and `uv run republic sync repair --issue 1 --dry-run` to preview canonicalization and orphan adoption.
Use `uv run republic sync health --issue 1 --format all` when you want one combined sync-ops snapshot before drilling into `sync check`, `sync repair`, or `clean`.
Use `uv run republic clean --sync-applied --dry-run` to preview manifest-aware retention before pruning old applied handoff groups.
Use `uv run republic dashboard --format all` to review both `Sync handoffs` and `Sync retention`, including prunable groups, prunable bytes, and oldest prunable age.

If you want to see an optional role pack in action, use:

```bash
cd examples/qa-role-pack
bash ../../scripts/demo_qa_role_pack.sh
```

If you want the local webhook receiver path with signature verification enabled, use:

```bash
cd examples/webhook-signature-receiver
bash ../../scripts/demo_webhook_signature_receiver.sh
```

If you want a production-oriented GitHub REST blueprint without executing live writes, use:

```bash
cd examples/live-github-ops
bash ../../scripts/demo_live_ops.sh
```

If you want to rehearse a publish-enabled sandbox rollout with stepwise safety changes, use:

```bash
cd examples/live-github-sandbox-rollout
bash ../../scripts/demo_live_publish_sandbox.sh
```

## 4. Switch to production mode

Edit `.ai-republic/reporepublic.yaml`:

```yaml
tracker:
  kind: github
  repo: owner/name
  mode: rest
llm:
  mode: codex
codex:
  command: codex
  model: gpt-5.4
```

Then export a token and start polling:

```bash
export GITHUB_TOKEN=...
uv run republic doctor
uv run republic github smoke --require-write-ready
uv run republic run
```

`github smoke --require-write-ready` now checks default-branch protection, PR review requirements, required status checks, and repo metadata push permission before you enable unattended draft-PR publish.

For event-driven execution instead of polling:

```bash
uv run republic trigger 123 --dry-run
uv run republic webhook --event issues --payload webhook.json --dry-run
```

## 5. Inspect results

- artifacts: `.ai-republic/artifacts/issue-<id>/<run-id>/`
- debug artifacts when enabled: `<role>.prompt.txt`, `<role>.raw-output.txt`
- workspaces: `.ai-republic/workspaces/issue-<id>/<run-id>/repo/`
- run state: `.ai-republic/state/runs.json`
- dashboard: `.ai-republic/dashboard/index.html`
- dashboard JSON snapshot: `.ai-republic/dashboard/index.json`
- dashboard Markdown snapshot: `.ai-republic/dashboard/index.md`
- sync audit reports: `.ai-republic/reports/sync-audit.json`, `.ai-republic/reports/sync-audit.md`
- sync health reports: `.ai-republic/reports/sync-health.json`, `.ai-republic/reports/sync-health.md`
- ops brief snapshots: `.ai-republic/reports/ops-brief.json`, `.ai-republic/reports/ops-brief.md`
- bundle landing files: `.ai-republic/reports/ops/<timestamp>/index.html`, `.ai-republic/reports/ops/<timestamp>/README.md`
- cleanup reports: `.ai-republic/reports/cleanup-preview.json`, `.ai-republic/reports/cleanup-result.json`
- optional JSONL logs: `.ai-republic/logs/reporepublic.jsonl`
- doctor snapshots: `.ai-republic/reports/doctor.json`, `.ai-republic/reports/doctor.md`
- status snapshots: `.ai-republic/reports/status.json`, `.ai-republic/reports/status.md`
- release preview snapshots: `.ai-republic/reports/release-preview.json`, `.ai-republic/reports/release-preview.md`
- GitHub release notes preview: `.ai-republic/reports/release-notes-v<version>.md`
- release announcement pack: `.ai-republic/reports/release-announce.json`, `.ai-republic/reports/release-announce.md`
- release checklist: `.ai-republic/reports/release-checklist.json`, `.ai-republic/reports/release-checklist.md`
- channel copy snippets: `.ai-republic/reports/announcement-v<version>.md`, `discussion-v<version>.md`, `social-v<version>.md`, `release-cut-v<version>.md`
- release asset report: `.ai-republic/reports/release-assets.json`, `.ai-republic/reports/release-assets.md`
- release asset summary: `.ai-republic/reports/release-assets-v<tag>.md`
- single issue status: `uv run republic status --issue 123`
- export operator health snapshots: `uv run republic doctor --format all` and `uv run republic status --format all`
- preview the next public tag cut: `uv run republic release preview --format all`
- generate the release copy pack: `uv run republic release announce --format all`
- run the full release preflight gate: `uv run republic release check --format all`
- validate local release assets: `uv run republic release assets --build --smoke-install --format all`
- run one issue immediately: `uv run republic trigger 123`
- validate a GitHub webhook payload: `uv run republic webhook --event issues --payload webhook.json --dry-run`
- force an immediate retry: `uv run republic retry 123`
- preview stale local cleanup: `uv run republic clean --dry-run`
- preview manifest-aware sync archive cleanup: `uv run republic clean --sync-applied --dry-run`
- export cleanup preview/report: `uv run republic clean --sync-applied --dry-run --report --report-format all`
- inspect applied manifest integrity: `uv run republic sync check --issue 123`
- preview manifest repair: `uv run republic sync repair --issue 123 --dry-run`
- export a combined sync-ops snapshot: `uv run republic sync health --issue 123 --format all`
- export a sync audit bundle: `uv run republic sync audit --format all`
- regenerate the local dashboard: `uv run republic dashboard`
- generate a dashboard with timed reload: `uv run republic dashboard --refresh-seconds 30`
- export HTML, JSON, and Markdown together: `uv run republic dashboard --format all`

## Presets

- `python-library`: Python package or service repo
- `web-app`: frontend or full-stack app
- `docs-only`: documentation-first repository
- `research-project`: notebook or experiment-heavy codebase

## Safety defaults

- merge remains human-controlled
- dry-run blocks all external writes
- PR opening is disabled by default
- dirty working trees warn by default and can be switched to `block` or `allow`
- sensitive diffs are escalated to reviewer notes and policy guardrails
