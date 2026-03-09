# Sandbox Rollout Open Order

Read the staged rollout artifacts in this order:

1. `baseline/doctor.md`
2. `baseline/github-smoke.md`
3. `comments-ready/github-smoke.md`
4. `pr-gated/github-smoke.md`
5. `pr-gated/require-write-ready.exit-code`
6. `pr-ready/github-smoke.md`
7. `pr-ready/require-write-ready.exit-code`
8. `.ai-republic/reports/ops/sandbox-pr-ready/index.html`
9. `.ai-republic/reports/ops/sandbox-pr-ready/ops-brief.md`
10. `.ai-republic/reports/ops/sandbox-pr-ready/github-smoke.md`
11. `.ai-republic/reports/ops/sandbox-pr-ready/ops-status.md`
12. `.ai-republic/dashboard/index.html`
13. `ops/execution-order.md`

The important gate is step 5 versus step 7:

- `pr-gated` must still fail `--require-write-ready`
- `pr-ready` must pass before you carry the rollout pattern into a real sandbox repository
