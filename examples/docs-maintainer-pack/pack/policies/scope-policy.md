# Scope Policy

Pack: `docs-maintainer-pack`

This repository is documentation-first. Favor Markdown, quickstarts, examples, and reference text before any code path.

## Rules

- Prefer `README.md`, `QUICKSTART.md`, `docs/`, and example snippets.
- Keep commands copy/paste friendly and call out assumptions in the summary.
- If an issue appears to require code changes, leave that need in the plan and review artifacts unless a maintainer explicitly widens scope.
- Treat release/deploy/auth examples as sensitive docs that still require careful human review.

## Always out of scope without human approval

- Runtime logic changes
- Build, deployment, or auth configuration rewrites
- Secrets or credential files
- Large destructive deletions
