# Operations Runbook

This runbook is the day-2 operating guide for RepoAgents maintainers.

## Scope

Use this document when you need to:

- start or stop routine repository maintenance
- inspect a failed or stuck run
- re-run a specific issue safely
- validate webhook-driven execution
- review runtime artifacts, logs, and dashboard output

## Primary operator loop

Normal operating flow:

1. Check environment health with `uv run repoagents doctor`
2. Inspect the latest state with `uv run repoagents status`
3. Render the local dashboard with `uv run repoagents dashboard`
4. Run the polling loop with `uv run repoagents run`
5. Use `uv run repoagents service start` when you want a detached repo-local worker
6. Use `uv run repoagents trigger <issue-id>` or `uv run repoagents webhook ...` for targeted intervention

## Command reference

```bash
uv run repoagents doctor
uv run repoagents doctor --format all
uv run repoagents run
uv run repoagents run --once
uv run repoagents run --dry-run
uv run repoagents service start
uv run repoagents service status
uv run repoagents service restart
uv run repoagents service stop
uv run repoagents trigger 123
uv run repoagents trigger 123 --dry-run
uv run repoagents webhook --event issues --payload webhook.json --dry-run
uv run repoagents status
uv run repoagents status --issue 123
uv run repoagents status --format all
uv run repoagents ops snapshot --archive
uv run repoagents ops status
uv run repoagents ops status --format all
uv run repoagents github smoke --require-write-ready
uv run repoagents ops snapshot --include-cleanup-preview --include-cleanup-result --include-sync-check --include-sync-repair-preview --archive
uv run repoagents ops snapshot --archive --history-limit 10 --prune-history
```

`uv run repoagents service restart` waits for the current worker to stop before launching a replacement. `uv run repoagents service stop` also clears a stale worker record when the saved pid is already gone.
The command also refreshes:

- `.ai-repoagents/reports/ops/latest.json`
- `.ai-repoagents/reports/ops/latest.md`
- `.ai-repoagents/reports/ops/history.json`
- `.ai-repoagents/reports/ops/history.md`
- `.ai-repoagents/reports/ops-status.json`
- `.ai-repoagents/reports/ops-status.md`
- `.ai-repoagents/reports/ops-brief.json`
- `.ai-repoagents/reports/ops-brief.md`

Use `--prune-history` only for bundle/archive paths managed under `.ai-repoagents/reports/ops/`. External custom output directories remain indexed but are not deleted by ops history pruning.
uv run repoagents sync ls
uv run repoagents sync show local-markdown/issue-1/<timestamp>-comment.md
uv run repoagents sync health --issue 1 --format all
uv run repoagents sync check --issue 1
uv run repoagents sync repair --issue 1 --dry-run
uv run repoagents sync audit --format all
uv run repoagents sync apply --issue 1 --tracker local-file --action comment --latest
uv run repoagents sync apply --issue 1 --tracker local-markdown --action comment --latest
uv run repoagents clean --sync-applied --dry-run
uv run repoagents clean --sync-applied --dry-run --report --report-format all
uv run repoagents retry 123
uv run repoagents clean --dry-run
uv run repoagents clean
uv run repoagents dashboard
uv run repoagents dashboard --format all
```

## Runtime locations

- config: `.ai-repoagents/repoagents.yaml`
- state: `.ai-repoagents/state/runs.json`
- artifacts: `.ai-repoagents/artifacts/issue-<id>/<run-id>/`
- workspaces: `.ai-repoagents/workspaces/issue-<id>/<run-id>/repo/`
- dashboard: `.ai-repoagents/dashboard/index.html`
- dashboard JSON snapshot: `.ai-repoagents/dashboard/index.json`
- doctor snapshots: `.ai-repoagents/reports/doctor.json`, `.ai-repoagents/reports/doctor.md`
- status snapshots: `.ai-repoagents/reports/status.json`, `.ai-repoagents/reports/status.md`
- ops status snapshots: `.ai-repoagents/reports/ops-status.json`, `.ai-repoagents/reports/ops-status.md`
- dashboard Markdown snapshot: `.ai-repoagents/dashboard/index.md`
- sync health reports: `.ai-repoagents/reports/sync-health.json`, `.ai-repoagents/reports/sync-health.md`
- sync audit reports: `.ai-repoagents/reports/sync-audit.json`, `.ai-repoagents/reports/sync-audit.md`
- cleanup reports: `.ai-repoagents/reports/cleanup-preview.json`, `.ai-repoagents/reports/cleanup-result.json`
- logs when enabled: `.ai-repoagents/logs/repoagents.jsonl`
- sync staging: `.ai-repoagents/sync/<tracker>/issue-<id>/`
- sync applied archive: `.ai-repoagents/sync-applied/<tracker>/issue-<id>/`

## Dashboard sync handoffs and retention

The dashboard now includes `Sync handoffs` and `Sync retention` sourced from `.ai-repoagents/sync-applied/**/manifest.json`, an `Ops snapshots` section sourced from `.ai-repoagents/reports/ops/latest.*` and `history.*`, plus direct `Reports` links for sync audit, sync health, GitHub smoke, ops status, ops brief, and cleanup exports under `.ai-repoagents/reports/`.

Use `repoagents ops status` when you want the same ops index posture in one CLI/export surface, but with the latest bundle manifest component summaries, current handoff brief headline/severity, landing paths, and recent history preview included directly in the output.
When `ops-status.json` or `ops-brief.json` exists, the dashboard `Reports` section renders matching cards and cross-links them to related report exports referenced by the latest bundle. `repoagents ops snapshot` now writes `ops-status.json|md`, `ops-brief.json|md`, and, for live GitHub REST trackers, `github-smoke.json|md`, plus bundle landing files `index.html`, `README.md` inside the handoff bundle, and refreshes root `ops-status.json|md`, `ops-brief.json|md`, `sync-health.json|md`, and live `github-smoke.json|md` at the repo root, so both the handoff bundle and dashboard/report surfaces can follow the latest sync posture, landing summary, and GitHub publish readiness without a separate command.

Use it when you need to:

- inspect which staged publish proposals were already handled
- open archived `branch` / `pr` / `pr-body` bundle members from one place
- follow normalized links such as `metadata_artifact` after the original staged file has moved
- review which applied issue archives are `stable`, `prunable`, or `repair-needed`
- estimate cleanup impact with prunable group counts, prunable bytes, and oldest prunable age before running `clean`

Refresh all exports with:

```bash
uv run repoagents dashboard --format all
```

## Normal checks

Before starting live runs:

- confirm `codex --version` and `codex login`
- confirm `GITHUB_TOKEN` if the tracker is in live GitHub REST mode
- run `uv run repoagents doctor`
- run `uv run repoagents github smoke --require-write-ready` before enabling unattended live writes
- the smoke gate now expects default-branch protection, PR review requirements, required status checks, and readable GitHub repo permissions for draft-PR publish
- use a dedicated sandbox repo/issue for `REPOREPUBLIC_GITHUB_WRITE_E2E=1` and `REPOREPUBLIC_GITHUB_PR_E2E=1` tests; the comment test deletes its comment and the draft PR test closes the PR and deletes the branch during cleanup
- if the repo uses `workspace.strategy: worktree`, confirm the target repo is a valid Git work tree
- inspect `workspace.dirty_policy` before running against a locally modified repository

## Failure handling

### A run is `retry_pending`

1. Inspect the latest run: `uv run repoagents status --issue <id>`
2. Open the role artifacts for the failing run
3. Fix the underlying cause if needed
4. Force a new retry window: `uv run repoagents retry <id>`
5. Rebuild the dashboard: `uv run repoagents dashboard`

### A run is `failed`

Check these first:

- Codex CLI availability and login state
- GitHub auth, rate limit, or network health
- policy findings in reviewer artifacts
- dirty working tree or worktree setup problems

Then either:

- re-run one issue directly with `uv run repoagents trigger <id>`
- or schedule it back into retry with `uv run repoagents retry <id>`

### The polling loop appears idle

Use:

```bash
uv run repoagents status
uv run repoagents run --once
uv run repoagents dashboard
```

If `run --once` finds nothing:

- verify the tracker input source
- verify issue state and labels
- verify the issue fingerprint did not already complete
- use `trigger` for a one-off forced rerun when appropriate

### Webhook payload did not start a run

1. Save the payload to disk
2. Validate it with:

```bash
uv run repoagents webhook --event issues --payload webhook.json --dry-run
```

3. Confirm the payload maps to an open issue number
4. If the issue is intentionally already complete, use `trigger --force` only after human review

## Safe manual intervention

Use the least destructive option first:

1. `status --issue <id>` to inspect
2. `dashboard` to rebuild the view
3. `retry <id>` to reopen the run
4. `trigger <id> --dry-run` to preview one issue
5. `trigger <id>` to execute one issue
6. `clean --dry-run` before any cleanup

Avoid deleting state or workspace files by hand unless the CLI cleanup path cannot recover.

## Offline publish handoff

When a tracker stages publish proposals locally instead of applying them directly:

1. inspect the inventory with `uv run repoagents sync ls`
2. open one artifact with `uv run repoagents sync show ...`
3. apply supported tracker helpers with `uv run repoagents sync apply ...` when appropriate, for example `local-file` or `local-markdown` comment and label proposals
4. copy any remaining handoff proposal manually
5. review the archive under `.ai-repoagents/sync-applied/` and the dashboard `Sync handoffs` / `Sync retention` sections
6. use `uv run repoagents clean --sync-applied --dry-run` before pruning old applied handoff groups
   Capture a shareable machine-readable cleanup preview with `--report --report-format all` when the cleanup needs review.
7. use `uv run repoagents sync health --issue <id> --format all` when you want one combined snapshot before choosing between repair, audit, or cleanup
8. if manifest drift is suspected, run `uv run repoagents sync check --issue <id>` before `sync repair`
9. export `uv run repoagents sync audit --issue <id> --format all` when you need a narrower shareable audit snapshot

## Human approval boundary

RepoAgents remains conservative by default:

- reviewer approval does not merge code
- dangerous diffs still require human judgment
- docs/tests changes may open a draft PR depending on policy, but merge stays manual
- secrets, CI/CD changes, auth-sensitive paths, and large deletions should be reviewed as incidents
- use `repoagents approval ls` / `repoagents approval show <issue-id>` to inspect pending publication actions
- `repoagents approval approve|reject <issue-id>` records the maintainer decision and artifacts; publish remains manual in this slice

## Recommended routine

Daily:

- `doctor`
- `status`
- `dashboard`

For each incident:

- inspect the failing run
- collect artifacts and logs
- decide whether to `retry`, `trigger`, or leave the issue pending

Weekly:

- clean stale local data with `clean --dry-run` then `clean`
- review template drift with `repoagents init --upgrade`

## Related examples

- live GitHub ops blueprint: [../examples/live-github-ops/README.md](../examples/live-github-ops/README.md)
- live GitHub rollout walkthrough: [./live-github-ops.md](./live-github-ops.md)
- sandbox publish rollout example: [../examples/live-github-sandbox-rollout/README.md](../examples/live-github-sandbox-rollout/README.md)
- sandbox publish rollout walkthrough: [./live-github-sandbox-rollout.md](./live-github-sandbox-rollout.md)
- local webhook receiver: [../examples/webhook-receiver/README.md](../examples/webhook-receiver/README.md)
- signed local webhook receiver: [../examples/webhook-signature-receiver/README.md](../examples/webhook-signature-receiver/README.md)
