# Example Local Markdown Sync

This sample repository demonstrates `tracker.kind: local_markdown` with sidecar sync staging.

## Files

- `parser.py`: tiny parser module with an empty-input bug.
- `tests/test_parser.py`: minimal parser tests.
- `issues/`: Markdown issue inbox consumed by `tracker.kind: local_markdown`.
- `.ai-republic/sync/local-markdown/`: generated at runtime with staged comments, branch proposals, PR drafts, and label suggestions.

## Demo

```bash
bash scripts/demo_local_markdown_sync.sh
```

The demo initializes RepoRepublic with the deterministic mock backend, enables `allow_open_pr`, triggers issue `#1`, runs `republic sync ls --issue 1`, applies the newest staged comment with `republic sync apply`, then applies the related branch/PR handoff with `--bundle`, and archives handled artifacts under `.ai-republic/sync-applied/local-markdown/issue-1/`.

Useful follow-up commands inside the demo workspace:

```bash
uv run republic sync ls --issue 1
uv run republic sync apply --issue 1 --tracker local-markdown --action comment --latest
uv run republic sync apply --issue 1 --tracker local-markdown --action pr-body --latest --bundle
uv run republic sync ls --scope applied --issue 1
uv run republic sync show local-markdown/issue-1/<timestamp>-comment.md
```
