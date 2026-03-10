# Example Docs Maintainer Pack

This sample repository demonstrates a repo-local custom maintainer pack for documentation-heavy work.

It does not add a new runtime role name. Instead, it customizes the existing RepoAgents control plane with local role guidance, prompt templates, policy files, and extra `AGENTS.md` instructions.

## What it shows

- `docs-only` preset as the starting scaffold
- repo-local overrides for `.ai-repoagents/roles/`
- repo-local overrides for `.ai-repoagents/prompts/`
- repo-local overrides for `.ai-repoagents/policies/`
- extra human guidance appended to `AGENTS.md`

## Files

- `README.md`: intentionally simple project overview without a strong quickstart section
- `QUICKSTART.md`: short manual setup steps
- `issues.json`: fixture issues for the demo run
- `pack/`: the custom maintainer pack files copied into `.ai-repoagents/` after `repoagents init`

## Demo

```bash
bash scripts/demo_docs_maintainer_pack.sh
```

Equivalent manual flow:

```bash
uv run repoagents init --preset docs-only --fixture-issues issues.json --tracker-repo demo/docs-maintainer-pack --backend mock
cp -R pack/roles/. .ai-repoagents/roles/
cp -R pack/prompts/. .ai-repoagents/prompts/
cp -R pack/policies/. .ai-repoagents/policies/
cat pack/AGENTS.append.md >> AGENTS.md
uv run repoagents trigger 1
uv run repoagents dashboard
```

After the run, inspect:

- `.ai-repoagents/roles/planner.md`
- `.ai-repoagents/prompts/planner.txt.j2`
- `.ai-repoagents/policies/scope-policy.md`
- `AGENTS.md`
- `.ai-repoagents/artifacts/issue-1/<run-id>/`
