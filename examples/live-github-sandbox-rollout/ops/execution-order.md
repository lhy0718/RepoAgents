# Sandbox Execution Open Order

After the publish gate is green, inspect the execution rehearsal in this order:

1. `.ai-republic/reports/sandbox-execution/trigger-dry-run.txt`
2. `.ai-republic/reports/sandbox-execution/trigger.txt`
3. `.ai-republic/reports/sandbox-execution/status.md`
4. `.ai-republic/artifacts/issue-201/<run-id>/triage.md`
5. `.ai-republic/artifacts/issue-201/<run-id>/planner.md`
6. `.ai-republic/artifacts/issue-201/<run-id>/engineer.md`
7. `.ai-republic/artifacts/issue-201/<run-id>/reviewer.md`
8. `.ai-republic/reports/ops/sandbox-issue-201/index.html`
9. `.ai-republic/reports/ops/sandbox-issue-201/ops-brief.md`
10. `.ai-republic/reports/ops/sandbox-issue-201/ops-status.md`

This execution step uses:

- `tracker.mode=fixture`
- `tracker.fixtures_path=issues.json`
- `llm.mode=mock`

The example restores the config to live `tracker.mode=rest` and `llm.mode=codex` after the run so the repository ends in publish-enabled sandbox posture.
