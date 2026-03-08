# Example Live GitHub Ops

This sample repository is a production-oriented RepoRepublic blueprint.

## What it shows

- live GitHub tracker mode with `tracker.kind: github` and `tracker.mode: rest`
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

## Demo

```bash
bash scripts/demo_live_ops.sh
```

This demo prepares the repository for live operation without making external writes. It initializes RepoRepublic, patches the config for live GitHub mode, enables file logging and `worktree`, initializes a local Git repository, and renders HTML, JSON, and Markdown dashboard exports.

## Next steps

1. Copy `ops/republic.env.example` to your real environment management system.
2. Set `tracker.repo` to the real GitHub repository slug.
3. Export `GITHUB_TOKEN`.
4. Run `bash ops/run-loop.sh`.
5. Follow the operator walkthrough in [../../docs/live-github-ops.md](../../docs/live-github-ops.md).
