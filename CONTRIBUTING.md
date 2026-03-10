# Contributing to RepoAgents

RepoAgents is designed as an issue-driven repository operations framework. Contributions should preserve that bias toward deterministic behavior, conservative safety defaults, and repo-local policy control.

## Ground rules

- Keep Codex CLI as the default worker runtime unless the change is explicitly about backend extensibility.
- Prefer additive, testable changes over broad refactors.
- Default to human approval and non-destructive rollout paths.
- Update both English and Korean docs when you change primary user-facing behavior.

## Local setup

```bash
git clone <your-fork> RepoAgents
cd RepoAgents
uv sync --dev
uv run pytest -q
```

Recommended checks before opening a PR:

```bash
uv run pytest -q
uv build
```

If your change touches live GitHub or Codex integration, keep those tests opt-in and document the required environment variables.

## Contribution workflow

1. Create a branch from `main`.
2. Make a focused change.
3. Add or update tests.
4. Update docs, examples, and backlog notes when behavior changes.
5. Run the local verification commands.
6. Open a pull request with:
   - problem statement
   - approach summary
   - test evidence
   - rollout or compatibility notes when relevant

## What to update with code changes

- Code paths under `src/`
- Tests under `tests/`
- User docs in `README.md`, `QUICKSTART.md`, or `docs/`
- Example scripts under `scripts/` or `examples/`
- Backlog status in `TODO.md` and `docs/backlog/issue-queue.md` for major work items

## Examples and docs

When adding a new top-level guide:

- add the English file first
- add the Korean counterpart beside it
- register both in `README.md`, `README.ko.md`, `docs/README.md`, and `docs/README.ko.md` if the guide is a primary entry point

When adding a new runnable example:

- add a dedicated `examples/<name>/README.md`
- add or update a `scripts/demo_*.sh` entry when the example is intended for first-run validation
- add a test in `tests/test_demo_scripts.py` when the example is expected to stay runnable

## Pull request expectations

- Keep PRs reviewable in size when possible.
- Call out changes to safety policy, publish behavior, or live GitHub paths explicitly.
- Do not remove or weaken guardrails without a clear reason and tests.
- Treat mock backend paths as deterministic contract surfaces, not throwaway demos.

## Release-facing changes

If the PR changes packaging, release process, or governance docs, also update:

- `CHANGELOG.md`
- `docs/release.md`
- `.github/workflows/ci.yml` when CI behavior changes
