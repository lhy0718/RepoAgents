# Role Pack Examples

RepoAgents keeps the core role pipeline small, but you can extend `roles.enabled` to activate optional built-in roles.

## Current built-in role packs

### QA gate

Purpose:

- add an explicit QA pass between engineering and review
- surface validation gaps before reviewer approval
- keep the pipeline deterministic in mock-backed demos

Config snippet:

```yaml
roles:
  enabled:
    - triage
    - planner
    - engineer
    - qa
    - reviewer
```

What changes:

- `qa` receives the engineer result and review signals
- it emits `qa.json` and `qa.md` artifacts
- reviewer can use the extra role results when making the final decision

Runnable example:

- [examples/qa-role-pack/README.md](../examples/qa-role-pack/README.md)
- [scripts/demo_qa_role_pack.sh](../scripts/demo_qa_role_pack.sh)

## Repo-local custom maintainer packs

You do not need a new runtime role name to create a custom pack.

A practical custom pack can:

- keep the core role order unchanged
- override `.ai-repoagents/roles/*.md`
- override selected `.ai-repoagents/prompts/*.txt.j2`
- override `.ai-repoagents/policies/*.md`
- append repo-specific instructions to `AGENTS.md`

### Docs maintainer pack

Purpose:

- specialize the default pipeline for documentation-first repositories
- keep scope inside Markdown, quickstarts, and reference docs
- show how a repo can bundle its own role/prompt/policy overrides after `repoagents init`

Runnable example:

- [examples/docs-maintainer-pack/README.md](../examples/docs-maintainer-pack/README.md)
- [scripts/demo_docs_maintainer_pack.sh](../scripts/demo_docs_maintainer_pack.sh)

## Choosing a role pack

Use the default four-role path when:

- you want the simplest maintainer loop
- you do not need an extra validation stage

Use the QA gate pack when:

- code changes need an explicit test/coverage checkpoint
- you want artifacts that separate engineering output from validation guidance
- you are evaluating how optional built-in roles behave before adding custom ones

Use a repo-local custom maintainer pack when:

- you want to specialize prompts and policy for one repository without changing Python runtime code
- the core four-role pipeline is still enough, but the instructions need to be sharper
- you want to prove a domain-specific pack before building a new built-in role

## Constraints

- the core order must remain `triage -> planner -> engineer -> reviewer`
- `qa` can only be inserted between `engineer` and `reviewer`
- duplicate role names are not allowed

## Future packs

The current codebase is ready for more built-in or custom examples such as:

- `security-review`
- `docs-editor`
- `release-manager`

Those would follow the same pattern: add the role class, expose it through the registry, document the config sequence, and provide a runnable example.
