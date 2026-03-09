# Live GitHub Ops Preflight

Before enabling live issue processing:

1. Confirm `codex --version` and `codex login`
2. Export `GITHUB_TOKEN`
3. Verify the repository has a clean Git baseline
4. Run `uv run republic doctor`
5. Run `uv run republic github smoke --require-write-ready`
6. Build a handoff rehearsal with `bash ops/build-handoff.sh`
7. Open `ops/handoff-order.md` and confirm the generated bundle matches the expected reading order
8. Render the dashboard with `uv run republic dashboard --refresh-seconds 30`
9. Start the loop with `bash ops/run-loop.sh`

The bundled `ops/github-smoke.fixture.json` exists only for offline rehearsal. Remove `tracker.smoke_fixture_path` before using the same workflow against a real GitHub repository.
