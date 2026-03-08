# Live GitHub Operations Walkthrough

This guide turns the `examples/live-github-ops` blueprint into a step-by-step operator workflow for a real GitHub repository.

## When to use this guide

Use this document when you want to:

- move from fixture or mock demos into live GitHub issue polling
- keep Codex CLI as the default worker runtime
- run RepoRepublic continuously with conservative human approval
- operate from a local machine, VM, or simple process manager before building a larger platform

## Prerequisites

Before touching a live repository, confirm:

- `uv sync --dev` completed in the RepoRepublic checkout
- `codex --version` and `codex login` both work
- `GITHUB_TOKEN` is exported with read access to issues and write access only if you intend to post comments or open draft PRs
- the target repository is cloned locally and has a clean baseline
- you understand the active `merge_policy.mode` and `safety.*` settings

For the conservative default path, keep:

- `llm.mode: codex`
- `merge_policy.mode: human_approval`
- `safety.allow_write_comments: false` or tightly controlled
- `safety.allow_open_pr: false` until dry-runs and single-issue triggers look correct

## Reference files

The live blueprint example is here:

- [../examples/live-github-ops/README.md](../examples/live-github-ops/README.md)
- [../examples/live-github-ops/ops/preflight.md](../examples/live-github-ops/ops/preflight.md)
- [../examples/live-github-ops/ops/republic.env.example](../examples/live-github-ops/ops/republic.env.example)
- [../examples/live-github-ops/ops/run-loop.sh](../examples/live-github-ops/ops/run-loop.sh)
- [../examples/live-github-ops/ops/render-dashboard.sh](../examples/live-github-ops/ops/render-dashboard.sh)

## Step 1. Clone the target repository

Work from the real repository you want RepoRepublic to maintain.

```bash
git clone git@github.com:OWNER/REPO.git
cd REPO
git status --short
```

If the working tree is already dirty, either clean it first or set `workspace.dirty_policy` deliberately. For live operation, `block` is the safest default.

## Step 2. Initialize RepoRepublic into the repository

Run initialization from inside the target repository.

```bash
uv run --project /path/to/RepoRepublic republic init \
  --preset python-library \
  --tracker-repo OWNER/REPO
```

Adjust the preset if the repository is closer to `web-app`, `docs-only`, or `research-project`.

This creates:

- `.ai-republic/reporepublic.yaml`
- `AGENTS.md`
- `WORKFLOW.md`
- `.ai-republic/roles/`
- `.ai-republic/prompts/`
- `.ai-republic/policies/`

## Step 3. Switch the config to live GitHub mode

Open `.ai-republic/reporepublic.yaml` and confirm the live path values.

Recommended baseline:

```yaml
tracker:
  kind: github
  mode: rest
  repo: OWNER/REPO
  poll_interval_seconds: 300

workspace:
  strategy: worktree
  dirty_policy: block

logging:
  json: true
  file_enabled: true

llm:
  mode: codex

merge_policy:
  mode: human_approval

safety:
  allow_write_comments: false
  allow_open_pr: false
```

Why these settings:

- `tracker.mode: rest` uses the live GitHub adapter
- `workspace.strategy: worktree` is more practical for larger repositories
- `logging.file_enabled: true` leaves an operator trail in `.ai-republic/logs/reporepublic.jsonl`
- `human_approval` keeps merge and publication conservative during rollout

## Step 4. Export environment variables

Use the blueprint env file as the starting point.

```bash
cp /path/to/RepoRepublic/examples/live-github-ops/ops/republic.env.example ./.ai-republic/republic.env
```

Then export the variables through your shell, direnv, systemd environment, or another secrets manager.

Minimum live environment:

```bash
export GITHUB_TOKEN=...
```

If Codex CLI is already logged in locally, you do not need to place Codex credentials into the repository.

## Step 5. Run `doctor`

Before a single issue is executed, validate the environment.

```bash
uv run --project /path/to/RepoRepublic republic doctor
```

The expected healthy path is:

- config loads successfully
- Codex command is executable
- GitHub auth and network checks pass
- runtime directories are writable
- the repository is a valid git work tree if `worktree` mode is active
- no unexpected managed template drift is reported

Do not continue to live execution until `doctor` is clean or the remaining warnings are understood.

## Step 6. Dry-run one issue first

Use a targeted dry-run before starting the polling loop.

```bash
uv run --project /path/to/RepoRepublic republic trigger 123 --dry-run
```

Look for:

- the issue is selected correctly
- the role order is correct
- planner `likely_files` are plausible
- blocked side effects match policy
- the backend is `codex`, not `mock`

If the repo is not ready for a specific issue number yet, `republic run --dry-run --once` is also useful for previewing the next poll cycle.

## Step 7. Execute one issue before enabling the loop

After a clean dry-run, execute exactly one issue.

```bash
uv run --project /path/to/RepoRepublic republic trigger 123
uv run --project /path/to/RepoRepublic republic status --issue 123
```

Inspect the produced data:

- artifacts under `.ai-republic/artifacts/issue-123/<run-id>/`
- workspace under `.ai-republic/workspaces/issue-123/<run-id>/repo/` or the worktree path
- state in `.ai-republic/state/runs.json`
- logs in `.ai-republic/logs/reporepublic.jsonl`

If reviewer or policy guardrails request changes, treat that as the intended safety behavior during rollout.

## Step 8. Start the long-running loop

Once a single issue behaves as expected, start the loop.

```bash
bash /path/to/RepoRepublic/examples/live-github-ops/ops/run-loop.sh
```

That helper script is a thin wrapper around:

```bash
uv run republic run
```

Run it under a process supervisor for real operations, for example `systemd`, `launchd`, a container runtime, or a CI scheduled runner.

## Step 9. Render and inspect the dashboard

Generate the operator dashboard regularly.

```bash
bash /path/to/RepoRepublic/examples/live-github-ops/ops/render-dashboard.sh
```

Or directly:

```bash
uv run republic dashboard --refresh-seconds 30
```

Open `.ai-republic/dashboard/index.html` in a browser and use:

- search to find one issue quickly
- the status filter to isolate failures or retries
- timed refresh when the page stays open during active operations

## Step 10. Handle failures safely

Use the least destructive recovery path first.

For a failed or retry-pending issue:

```bash
uv run republic status --issue 123
uv run republic retry 123
uv run republic trigger 123 --dry-run
uv run republic trigger 123
```

Use `clean --dry-run` before any workspace cleanup:

```bash
uv run republic clean --dry-run
uv run republic clean
```

If the problem is GitHub auth, Codex login, rate limiting, or dirty worktree state, fix that cause before re-running the issue.

## Step 11. Open the write path gradually

Do not enable comments or draft PRs on day 1 unless the repository is already well understood.

Recommended rollout:

1. Start with `allow_write_comments: false` and `allow_open_pr: false`
2. After several clean single-issue runs, consider enabling issue comments
3. Only after reviewer and policy behavior look stable, consider `allow_open_pr: true`
4. Keep merges manual even when draft PR creation is enabled

## Optional: add webhook-driven entry points

Polling is enough for an MVP rollout, but webhook-driven execution is useful for faster reaction.

Relevant paths:

- [runbook.md](./runbook.md)
- [../examples/webhook-receiver/README.md](../examples/webhook-receiver/README.md)
- [../scripts/webhook_receiver.py](../scripts/webhook_receiver.py)

Validate webhook payloads with:

```bash
uv run republic webhook --event issues --payload webhook.json --dry-run
```

before wiring them into a live receiver.

## Rollout checklist

Before calling the deployment live, verify:

- `doctor` is clean
- at least one `trigger --dry-run` and one `trigger` completed successfully
- artifacts and logs are readable by operators
- the dashboard renders correctly
- `dirty_policy`, publication policy, and safety flags match the repo risk profile
- the human reviewer path is clear when RepoRepublic requests changes

## Related documents

- [runbook.md](./runbook.md)
- [extensions.md](./extensions.md)
- [../examples/live-github-ops/README.md](../examples/live-github-ops/README.md)
