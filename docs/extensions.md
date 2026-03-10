# Extensions

RepoAgents is intentionally modular. The MVP keeps the number of moving parts small, but the extension seams are already explicit.

## Add a backend

Implement `BackendRunner` in `src/repoagents/backend/base.py`:

- accept a `BackendInvocation`
- return a typed Pydantic model
- raise `BackendExecutionError` on failures

Then register it in `src/repoagents/backend/factory.py`.

Use cases:

- different Codex execution profiles
- alternative local model runners
- staged review-only backends

## Add a tracker

Implement `Tracker` in `src/repoagents/tracker/base.py`:

- `list_open_issues`
- `get_issue`
- `post_comment`
- `create_branch`
- `open_pr`
- `set_issue_label`

Then wire it into `src/repoagents/tracker/factory.py`.

The built-in adapters now are:

- `github`: live REST mode plus fixture replay
- `local_file`: JSON inbox for local and offline orchestration, with optional sidecar sync staging under `.ai-repoagents/sync/local-file/`
- `local_markdown`: Markdown issue directory for local and offline orchestration, with optional sidecar sync staging under `.ai-repoagents/sync/local-markdown/`

Runnable examples:

- `examples/python-lib`: GitHub tracker in fixture mode
- `examples/web-app`: GitHub tracker in fixture mode for a lightweight app repo
- `examples/local-file-inbox`: `local_file` tracker with an offline JSON inbox
- `examples/local-file-sync`: `local_file` tracker with staged local sync proposals and `sync apply`
- `examples/local-markdown-inbox`: `local_markdown` tracker with a Markdown issue directory
- `examples/local-markdown-sync`: `local_markdown` tracker with staged comment and draft-PR proposals written locally
- `examples/webhook-receiver`: local HTTP receiver that forwards GitHub-style POSTs into `repoagents webhook`
- `examples/webhook-signature-receiver`: local HTTP receiver with shared-secret signature verification before forwarding accepted payloads
- `examples/live-github-ops`: production-oriented GitHub REST blueprint with `worktree`, file logging, and ops helper files

For event-driven flows, GitHub webhook payload parsing lives in `src/repoagents/orchestrator/webhooks.py`. Additional providers can follow the same pattern: normalize an incoming event into a single issue id, then call the orchestrator single-issue execution path instead of the polling loop.

For the shared sync inventory contract and CLI, see [sync.md](./sync.md).

## Extend sync handlers

Tracker-specific sync apply behavior is registered through `SyncActionRegistry` in [src/repoagents/sync_artifacts.py](../src/repoagents/sync_artifacts.py).

That registry currently supports:

- tracker/action-specific apply handlers such as `comment` or `labels`
- tracker-level bundle resolvers for related handoff sets like `branch -> pr -> pr-body`
- wildcard fallback handlers for archive-only actions

The parsed `SyncArtifact` also exposes provider-neutral normalized fields:

- `artifact_role`
- `issue_key`
- `bundle_key`
- `refs`
- `links`

This is the seam to use when a new offline tracker needs custom `sync apply` behavior without changing the CLI surface.

## Add workspace strategies

Implement `WorkspaceManager` in `src/repoagents/workspace/base.py`.

The built-in strategies are `copy` and `worktree`. Additional strategies can reuse the same orchestrator contract:

- `prepare_workspace(issue, run_id) -> Path`
- optional `cleanup_workspace(workspace_path) -> None`

## Customize roles

Each role uses:

- a markdown charter in `.ai-repoagents/roles/`
- a prompt template in `.ai-repoagents/prompts/`
- a typed output model in `src/repoagents/models/domain.py`

To add or replace role behavior:

1. create or edit the role template files
2. update the role class under `src/repoagents/roles/`
3. update the schema model if the output contract changes
4. add tests for prompt rendering and backend parsing

The built-in role registry currently supports:

- `triage`
- `planner`
- `engineer`
- `qa`
- `reviewer`

`roles.enabled` controls execution order. The core path must remain `triage -> planner -> engineer -> reviewer`, and `qa` is the current example of an optional built-in role that can run between `engineer` and `reviewer`.

For a runnable role-pack example, see [role-packs.md](./role-packs.md) and [examples/qa-role-pack/README.md](../examples/qa-role-pack/README.md).

## Customize policies

Policy checks live in `src/repoagents/policies/guardrails.py`.

This is the right place to add:

- path-based restrictions
- diff size thresholds
- repo-specific escalation rules
- auto-merge candidate classification

The human-facing policy documents under `.ai-repoagents/policies/` should stay in sync with these checks.

## Generated templates

`repoagents init` copies and renders templates from `src/repoagents/templates/default/`.

You can extend the scaffolding system by adding:

- new presets in `src/repoagents/templates/scaffold.py`
- new prompt templates
- new policy documents
- additional workflow files

## Extend the dashboard

The static operations view lives in `src/repoagents/dashboard.py`.

This is the place to add:

- richer run cards or filters
- new links into artifacts and logs
- alternate output formats beyond the current HTML, JSON, and Markdown exports

## Testing strategy

When extending RepoAgents, keep three levels of tests:

1. config and CLI tests for setup and operator flows
2. backend/role tests for structured output contracts
3. orchestrator tests for retries, state, scheduling, and duplicate prevention
