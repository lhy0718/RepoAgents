# Example Docs Maintainer Pack

This sample repository demonstrates a repo-local custom maintainer pack for documentation-heavy work.

It does not add a new runtime role name. Instead, it customizes the existing RepoRepublic control plane with local role guidance, prompt templates, policy files, and extra `AGENTS.md` instructions.

## What it shows

- `docs-only` preset as the starting scaffold
- repo-local overrides for `.ai-republic/roles/`
- repo-local overrides for `.ai-republic/prompts/`
- repo-local overrides for `.ai-republic/policies/`
- extra human guidance appended to `AGENTS.md`

## Files

- `README.md`: intentionally simple project overview without a strong quickstart section
- `QUICKSTART.md`: short manual setup steps
- `issues.json`: fixture issues for the demo run
- `pack/`: the custom maintainer pack files copied into `.ai-republic/` after `republic init`

## Demo

```bash
bash scripts/demo_docs_maintainer_pack.sh
```

Equivalent manual flow:

```bash
uv run republic init --preset docs-only --fixture-issues issues.json --tracker-repo demo/docs-maintainer-pack --backend mock
cp -R pack/roles/. .ai-republic/roles/
cp -R pack/prompts/. .ai-republic/prompts/
cp -R pack/policies/. .ai-republic/policies/
cat pack/AGENTS.append.md >> AGENTS.md
uv run republic trigger 1
uv run republic dashboard
```

After the run, inspect:

- `.ai-republic/roles/planner.md`
- `.ai-republic/prompts/planner.txt.j2`
- `.ai-republic/policies/scope-policy.md`
- `AGENTS.md`
- `.ai-republic/artifacts/issue-1/<run-id>/`
