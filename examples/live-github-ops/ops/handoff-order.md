# Live Handoff Reading Order

Use this order when you receive an incident handoff archive from the live GitHub rollout path.

1. Open `index.html` or `README.md` first.
2. Read `ops-brief.md` for the operator headline, top findings, and next actions.
3. Read `github-smoke.md` to verify live repo access, default-branch policy, and publish readiness.
4. Read `ops-status.md` to confirm which bundle is latest and which related reports were captured.
5. Open `dashboard.html` if you need the broader run/report surface.
6. Drop into `sync-health.md` and `sync-audit.md` only when sync posture or manifest integrity needs follow-up.

For the bundled offline rehearsal shipped in this example, `github-smoke.fixture.json` provides the live GitHub snapshot. Remove `tracker.smoke_fixture_path` before using the same workflow against a real repository.
