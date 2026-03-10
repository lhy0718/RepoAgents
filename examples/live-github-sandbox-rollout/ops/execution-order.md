# Sandbox Execution Open Order

After the publish gate is green, inspect the execution rehearsal in this order:

1. `.ai-repoagents/reports/sandbox-execution/trigger-dry-run.txt`
2. `.ai-repoagents/reports/sandbox-execution/trigger.txt`
3. `.ai-repoagents/reports/sandbox-execution/status.md`
4. `.ai-repoagents/artifacts/issue-201/<run-id>/triage.md`
5. `.ai-repoagents/artifacts/issue-201/<run-id>/planner.md`
6. `.ai-repoagents/artifacts/issue-201/<run-id>/engineer.md`
7. `.ai-repoagents/artifacts/issue-201/<run-id>/reviewer.md`
8. `.ai-repoagents/reports/ops/sandbox-issue-201/index.html`
9. `.ai-repoagents/reports/ops/sandbox-issue-201/ops-brief.md`
10. `.ai-repoagents/reports/ops/sandbox-issue-201/ops-status.md`

This execution step uses:

- `tracker.mode=fixture`
- `tracker.fixtures_path=issues.json`
- `llm.mode=mock`

The example restores the config to live `tracker.mode=rest` and `llm.mode=codex` after the run so the repository ends in publish-enabled sandbox posture.
