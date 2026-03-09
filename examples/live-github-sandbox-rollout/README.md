# Example Live GitHub Sandbox Rollout

This sample repository demonstrates a staged publish rollout for a sandbox GitHub repository.

## What it shows

- live GitHub tracker mode with `tracker.kind: github` and `tracker.mode: rest`
- offline `github smoke` rehearsal driven by `tracker.smoke_fixture_path`
- progressive policy changes from read-only to comment writes and then draft-PR writes
- rollout gates captured under `.ai-republic/reports/sandbox-rollout/<phase>/`
- final `ops snapshot` handoff bundle once draft-PR publish becomes ready

## Rollout phases

1. `baseline`
   `allow_write_comments=false`, `allow_open_pr=false`
2. `comments-ready`
   `allow_write_comments=true`, `allow_open_pr=false`
3. `pr-gated`
   `allow_write_comments=true`, `allow_open_pr=true`, but `github smoke --require-write-ready` still fails
4. `pr-ready`
   `allow_write_comments=true`, `allow_open_pr=true`, and `github smoke --require-write-ready` passes

## Files

- `parser.py`: tiny helper module kept intentionally simple
- `tests/test_parser.py`: minimal parser test
- `ops/republic.env.example`: environment variables to export in a sandbox repo
- `ops/preflight.md`: rollout checklist
- `ops/rollout-order.md`: which artifacts to inspect first during the rehearsal
- `ops/execution-order.md`: which execution artifacts to inspect after the publish gate turns green
- `ops/set-sandbox-phase.sh`: phase helper that patches `.ai-republic/reporepublic.yaml`
- `ops/rehearse-rollout.sh`: phase-by-phase rehearsal command
- `ops/rehearse-execution.sh`: deterministic single-issue execution after the rollout gate passes
- `ops/github-smoke.*.json`: offline smoke snapshots for each rollout phase
- `issues.json`: fixture issue used for the offline execution rehearsal

## Demo

```bash
bash scripts/demo_live_publish_sandbox.sh
```

This demo prepares a sandbox repository for staged publish enablement without making external writes. It initializes RepoRepublic, patches the config for live GitHub REST mode, sets a fake `GITHUB_TOKEN`, walks the four rollout phases, records per-phase `doctor` and `github smoke` reports, builds a final handoff bundle only after the `pr-ready` gate passes, then runs one deterministic issue execution and builds a second bundle that includes the real run artifacts.

The rehearsal scripts create local commits when they change `.ai-republic/reporepublic.yaml`. That keeps `workspace.dirty_policy: block` compatible with repeated `doctor` runs.

The generated rehearsal artifacts include:

- `.ai-republic/reports/sandbox-rollout/baseline/doctor.json|md`
- `.ai-republic/reports/sandbox-rollout/comments-ready/github-smoke.json|md`
- `.ai-republic/reports/sandbox-rollout/pr-gated/require-write-ready.exit-code`
- `.ai-republic/reports/sandbox-rollout/pr-ready/require-write-ready.exit-code`
- `.ai-republic/reports/sandbox-execution/trigger-dry-run.txt`
- `.ai-republic/reports/sandbox-execution/trigger.txt`
- `.ai-republic/reports/sandbox-execution/status.json|md`
- `.ai-republic/reports/ops/sandbox-pr-ready/`
- `.ai-republic/reports/ops/sandbox-issue-201/`
- root `.ai-republic/reports/github-smoke.json|md`
- root `.ai-republic/reports/ops-brief.json|md`
- root `.ai-republic/reports/ops-status.json|md`

Use [ops/rollout-order.md](./ops/rollout-order.md) as the fixed reading order.
Use [ops/execution-order.md](./ops/execution-order.md) for the execution rehearsal artifact order.

## Next steps

1. Replace `tracker.repo` with the real sandbox repository slug.
2. Replace the fake `GITHUB_TOKEN` with a real sandbox token.
3. Remove `tracker.smoke_fixture_path` after the offline rehearsal.
4. Re-run `uv run republic github smoke --require-write-ready` against the real sandbox repo.
5. Keep `allow_open_pr=false` until the sandbox smoke path is clean and reviewed.
6. Use `bash ops/rehearse-execution.sh` to connect the green sandbox posture to a deterministic issue run.
7. Follow [../../docs/live-github-sandbox-rollout.md](../../docs/live-github-sandbox-rollout.md) for the full operator walkthrough.
