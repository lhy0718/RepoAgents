# Example Local File Sync

This sample repository demonstrates `tracker.kind: local_file` with sidecar sync staging.

## Files

- `parser.py`: tiny parser module with an empty-input bug.
- `tests/test_parser.py`: minimal parser tests.
- `issues.json`: JSON issue inbox consumed by `tracker.kind: local_file`.
- `.ai-republic/sync/local-file/`: generated at runtime with staged comment proposals and other offline publication handoffs.

## Demo

```bash
bash scripts/demo_local_file_sync.sh
```

The demo initializes RepoRepublic with the deterministic mock backend, triggers issue `#1`, runs `republic sync ls --issue 1`, applies the newest staged comment with `republic sync apply`, and archives handled artifacts under `.ai-republic/sync-applied/local-file/issue-1/`.

Useful follow-up commands inside the demo workspace:

```bash
uv run republic sync ls --issue 1
uv run republic sync apply --issue 1 --tracker local-file --action comment --latest
uv run republic sync ls --scope applied --issue 1
uv run republic sync show local-file/issue-1/<timestamp>-comment.md
```
