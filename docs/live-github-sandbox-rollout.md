# Live GitHub Sandbox Publish Rollout

This guide shows how to rehearse progressive publish enablement in a sandbox GitHub repository before enabling the same settings in a production repository.

## When to use this guide

Use this document when you want to:

- keep `tracker.kind: github` and `tracker.mode: rest`
- validate `allow_write_comments` first, then `allow_open_pr`
- force `github smoke --require-write-ready` to gate draft-PR publish
- produce a final handoff bundle only after the sandbox gate turns green
- connect that green sandbox posture to one deterministic issue execution before touching a real repo

## Reference files

- [../examples/live-github-sandbox-rollout/README.md](../examples/live-github-sandbox-rollout/README.md)
- [../examples/live-github-sandbox-rollout/ops/preflight.md](../examples/live-github-sandbox-rollout/ops/preflight.md)
- [../examples/live-github-sandbox-rollout/ops/rollout-order.md](../examples/live-github-sandbox-rollout/ops/rollout-order.md)
- [../examples/live-github-sandbox-rollout/ops/execution-order.md](../examples/live-github-sandbox-rollout/ops/execution-order.md)
- [../examples/live-github-sandbox-rollout/ops/set-sandbox-phase.sh](../examples/live-github-sandbox-rollout/ops/set-sandbox-phase.sh)
- [../examples/live-github-sandbox-rollout/ops/rehearse-rollout.sh](../examples/live-github-sandbox-rollout/ops/rehearse-rollout.sh)
- [../examples/live-github-sandbox-rollout/ops/rehearse-execution.sh](../examples/live-github-sandbox-rollout/ops/rehearse-execution.sh)
- [../scripts/demo_live_publish_sandbox.sh](../scripts/demo_live_publish_sandbox.sh)

## Phase model

1. `baseline`
   No live writes are enabled. Use this to prove the repo, token, origin, and branch policy surfaces are readable.
2. `comments-ready`
   Comment writes are enabled, draft-PR writes are still disabled.
3. `pr-gated`
   Draft-PR writes are requested, but `github smoke --require-write-ready` must still fail.
4. `pr-ready`
   Draft-PR writes are requested and the readiness gate passes. Only now should you build a handoff bundle for review.

## Offline rehearsal

Run the bundled sandbox demo:

```bash
bash scripts/demo_live_publish_sandbox.sh
```

This prepares a temporary repository, sets a fake `GITHUB_TOKEN`, points `tracker.smoke_fixture_path` at the phase fixtures, records per-phase `doctor` and `github smoke` exports, builds the readiness bundle under `.ai-repoagents/reports/ops/sandbox-pr-ready/`, then switches temporarily into `github fixture + mock backend` mode to run one deterministic issue and build a second execution bundle under `.ai-repoagents/reports/ops/sandbox-issue-201/`.

During the rehearsal, the helper script creates local commits for each phase transition so `workspace.dirty_policy: block` remains valid while `doctor` is re-run.

The per-phase reports live under:

- `.ai-repoagents/reports/sandbox-rollout/baseline/`
- `.ai-repoagents/reports/sandbox-rollout/comments-ready/`
- `.ai-repoagents/reports/sandbox-rollout/pr-gated/`
- `.ai-repoagents/reports/sandbox-rollout/pr-ready/`

The critical gate files are:

- `.ai-repoagents/reports/sandbox-rollout/pr-gated/require-write-ready.exit-code`
- `.ai-repoagents/reports/sandbox-rollout/pr-ready/require-write-ready.exit-code`

Expected values:

- `pr-gated`: `1`
- `pr-ready`: `0`

## Deterministic execution rehearsal

After the publish gate is green, the example runs one issue in offline execution mode:

- `tracker.mode=fixture`
- `tracker.fixtures_path=issues.json`
- `llm.mode=mock`

That path writes:

- `.ai-repoagents/reports/sandbox-execution/trigger-dry-run.txt`
- `.ai-repoagents/reports/sandbox-execution/trigger.txt`
- `.ai-repoagents/reports/sandbox-execution/status.json|md`
- `.ai-repoagents/artifacts/issue-201/<run-id>/...`
- `.ai-repoagents/reports/ops/sandbox-issue-201/`

The repo is then restored to live `tracker.mode=rest` and `llm.mode=codex` so the final config still represents publish-enabled sandbox posture.

## Using the same flow in a real sandbox repository

1. Clone the sandbox repository locally.
2. Run `repoagents init` inside it.
3. Switch the config to `tracker.kind: github`, `tracker.mode: rest`, `workspace.strategy: worktree`, `logging.file_enabled: true`.
4. Start with:

```yaml
safety:
  allow_write_comments: false
  allow_open_pr: false
```

5. Run `uv run repoagents doctor`.
6. Run `uv run repoagents github smoke --format all`.
7. Enable comment writes only and repeat the smoke step.
8. Enable draft-PR writes in the sandbox and require:

```bash
uv run repoagents github smoke --require-write-ready
```

If this still exits non-zero, keep `allow_open_pr=true` disabled or revert it until the sandbox repo branch policy is corrected.

## Connect readiness to one issue execution

Before you let a real sandbox repository publish comments or draft PRs, run one deterministic issue rehearsal to prove the artifact flow:

1. Keep the same repository checkout and green `pr-ready` config.
2. Temporarily switch to a fixture issue source and deterministic backend.
3. Run one issue with `trigger`.
4. Inspect artifacts, status, and the execution handoff bundle.
5. Restore the live sandbox config before you leave the repo ready for real use.

The bundled helper already does this:

```bash
bash ops/rehearse-execution.sh
```

Open the execution artifacts in the order pinned by [../examples/live-github-sandbox-rollout/ops/execution-order.md](../examples/live-github-sandbox-rollout/ops/execution-order.md).

## Final handoff bundle

Only after `pr-ready` is clean should you generate a bundle:

```bash
uv run repoagents ops snapshot \
  --output-dir .ai-repoagents/reports/ops/sandbox-pr-ready \
  --include-sync-check \
  --include-sync-repair-preview \
  --archive
```

Then refresh:

```bash
uv run repoagents ops status --format all
uv run repoagents dashboard --refresh-seconds 30 --format all
```

Open the bundle in this order:

1. `index.html`
2. `ops-brief.md`
3. `github-smoke.md`
4. `ops-status.md`
5. `dashboard.html`

For the exact rehearsal sequence, follow [../examples/live-github-sandbox-rollout/ops/rollout-order.md](../examples/live-github-sandbox-rollout/ops/rollout-order.md).

## Safety notes

- Keep `merge_policy.mode: human_approval`.
- Treat sandbox publish as a rehearsal, not as production automation.
- Remove `tracker.smoke_fixture_path` before using the same commands against the real sandbox repository.
- Do not enable unattended writes in production until the sandbox path has already passed and the handoff bundle has been reviewed.
