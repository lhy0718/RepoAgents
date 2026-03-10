# Example Local File Sync

This sample repository demonstrates `tracker.kind: local_file` with sidecar sync staging.

## Files

- `parser.py`: tiny parser module with an empty-input bug.
- `tests/test_parser.py`: minimal parser tests.
- `issues.json`: JSON issue inbox consumed by `tracker.kind: local_file`.
- `.ai-repoagents/sync/local-file/`: generated at runtime with staged comment proposals and other offline publication handoffs.

## Demo

```bash
bash scripts/demo_local_file_sync.sh
```

The demo initializes RepoAgents with a deterministic offline fake `codex` shim, triggers issue `#1`, runs `repoagents sync ls --issue 1`, applies the newest staged comment with `repoagents sync apply`, and archives handled artifacts under `.ai-repoagents/sync-applied/local-file/issue-1/`.

Useful follow-up commands inside the demo workspace:

```bash
uv run repoagents sync ls --issue 1
uv run repoagents sync apply --issue 1 --tracker local-file --action comment --latest
uv run repoagents sync ls --scope applied --issue 1
uv run repoagents sync show local-file/issue-1/<timestamp>-comment.md
```
