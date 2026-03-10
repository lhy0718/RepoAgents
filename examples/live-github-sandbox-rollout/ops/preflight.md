# Sandbox Publish Rollout Preflight

Before enabling live comment or draft-PR writes in a sandbox repository:

1. Confirm `codex --version` and `codex login`
2. Export `GITHUB_TOKEN`
3. Verify the repository has a clean Git baseline and a matching `origin`
4. Run `uv run repoagents doctor`
5. Start with `allow_write_comments=false` and `allow_open_pr=false`
6. Walk the rollout phases with `bash ops/rehearse-rollout.sh`
7. Require `uv run repoagents github smoke --require-write-ready` to fail in `pr-gated`
8. Require the same command to pass in `pr-ready`
9. Run `bash ops/rehearse-execution.sh` to connect the green sandbox posture to one deterministic issue execution
10. Open `ops/rollout-order.md` and `ops/execution-order.md` before enabling unattended sandbox writes

The bundled `ops/github-smoke.*.json` files exist only for offline rehearsal. Remove `tracker.smoke_fixture_path` before using the same flow against the real sandbox repository.
