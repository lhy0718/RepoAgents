# Live GitHub Ops Preflight

Before enabling live issue processing:

1. Confirm `codex --version` and `codex login`
2. Export `GITHUB_TOKEN`
3. Verify the repository has a clean Git baseline
4. Run `uv run republic doctor`
5. Render the dashboard with `uv run republic dashboard --refresh-seconds 30`
6. Start the loop with `bash ops/run-loop.sh`
