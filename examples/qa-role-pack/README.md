# Example QA Role Pack

This sample repository demonstrates the optional `qa` role in the RepoAgents pipeline.

## What it shows

- `roles.enabled` extended to `triage -> planner -> engineer -> qa -> reviewer`
- `qa` artifacts emitted between engineering and review
- deterministic mock backend behavior for offline validation

## Files

- `parser.py`: tiny parser module with an empty-input bug.
- `tests/test_parser.py`: minimal parser tests.
- `issues.json`: fixture issues used for the demo run.

## Demo

```bash
bash scripts/demo_qa_role_pack.sh
```

Equivalent manual flow:

```bash
uv run repoagents init --preset python-library --fixture-issues issues.json --tracker-repo demo/qa-role-pack --backend mock
uv run repoagents trigger 1
uv run repoagents dashboard
```

After the run, inspect:

- `.ai-repoagents/artifacts/issue-1/<run-id>/qa.json`
- `.ai-repoagents/artifacts/issue-1/<run-id>/qa.md`
