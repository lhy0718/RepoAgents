# Example Live GitHub Ops

This sample repository is a production-oriented RepoRepublic blueprint.

## What it shows

- live GitHub tracker mode with `tracker.kind: github` and `tracker.mode: rest`
- offline rollout rehearsal with `tracker.smoke_fixture_path` for `github smoke` and `ops snapshot`
- `workspace.strategy: worktree` for larger repositories
- file logging enabled under `.ai-republic/logs/`
- dashboard generation with timed reload plus JSON/Markdown exports
- operator helper files under `ops/`

## Files

- `parser.py`: tiny parser module kept intentionally simple
- `tests/test_parser.py`: minimal parser tests
- `ops/republic.env.example`: environment variables to export in production
- `ops/run-loop.sh`: long-running orchestrator command
- `ops/render-dashboard.sh`: dashboard refresh command
- `ops/preflight.md`: production rollout checklist
- `ops/build-handoff.sh`: handoff bundle rehearsal command
- `ops/github-smoke.fixture.json`: offline live GitHub smoke snapshot used by the rehearsal flow
- `ops/handoff-order.md`: which files to open first inside the handoff bundle

## Demo

```bash
bash scripts/demo_live_ops.sh
```

This demo prepares the repository for live operation without making external writes. It initializes RepoRepublic, patches the config for live GitHub REST mode, enables file logging and `worktree`, points `tracker.smoke_fixture_path` at the bundled offline smoke snapshot, initializes a local Git repository with a matching `origin`, renders `github-smoke`, builds an `ops snapshot` handoff archive, refreshes `ops-status`, and renders HTML, JSON, and Markdown dashboard exports.

The generated handoff bundle lives under `.ai-republic/reports/ops/live-handoff-demo/` and includes:

- `index.html` / `README.md`
- `ops-brief.json|md`
- `github-smoke.json|md`
- `ops-status.json|md`
- `dashboard.html|json|md`
- `bundle.json|md`

Open-order guidance is pinned in [ops/handoff-order.md](./ops/handoff-order.md).

## Next steps

1. Copy `ops/republic.env.example` to your real environment management system.
2. Set `tracker.repo` to the real GitHub repository slug.
3. Export `GITHUB_TOKEN`.
4. Remove `tracker.smoke_fixture_path` after the offline rehearsal.
5. Run `uv run republic github smoke --require-write-ready` against the real repo.
6. Run `bash ops/run-loop.sh`.
7. Follow the operator walkthrough in [../../docs/live-github-ops.md](../../docs/live-github-ops.md).
