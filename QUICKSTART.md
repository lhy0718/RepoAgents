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
```

## 2. Initialize a target repo

```bash
cd /path/to/your/repo
uv run republic init
uv run republic init --preset python-library --tracker-repo owner/name
uv run republic init --tracker-kind local_file --tracker-path issues.json
uv run republic doctor
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
bash scripts/demo_web_app.sh
bash scripts/demo_local_file_tracker.sh
bash scripts/demo_local_file_sync.sh
bash scripts/demo_local_markdown_tracker.sh
bash scripts/demo_local_markdown_sync.sh
bash scripts/demo_qa_role_pack.sh
bash scripts/demo_webhook_receiver.sh
bash scripts/demo_webhook_signature_receiver.sh
bash scripts/demo_live_ops.sh
```

These scripts copy the example repos into temporary workspaces so the checked-in examples stay untouched.

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
```

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
uv run republic run
```

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
- cleanup reports: `.ai-republic/reports/cleanup-preview.json`, `.ai-republic/reports/cleanup-result.json`
- optional JSONL logs: `.ai-republic/logs/reporepublic.jsonl`
- single issue status: `uv run republic status --issue 123`
- run one issue immediately: `uv run republic trigger 123`
- validate a GitHub webhook payload: `uv run republic webhook --event issues --payload webhook.json --dry-run`
- force an immediate retry: `uv run republic retry 123`
- preview stale local cleanup: `uv run republic clean --dry-run`
- preview manifest-aware sync archive cleanup: `uv run republic clean --sync-applied --dry-run`
- export cleanup preview/report: `uv run republic clean --sync-applied --dry-run --report --report-format all`
- inspect applied manifest integrity: `uv run republic sync check --issue 123`
- preview manifest repair: `uv run republic sync repair --issue 123 --dry-run`
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
