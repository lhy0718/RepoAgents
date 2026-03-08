# Example Local Markdown Inbox

This sample repository demonstrates RepoRepublic with the `local_markdown` tracker.

## Files

- `parser.py`: tiny parser module with an empty-input bug.
- `tests/test_parser.py`: minimal parser tests.
- `issues/`: Markdown issue inbox consumed by `tracker.kind: local_markdown`.

## Demo

```bash
uv run republic init --preset python-library --tracker-kind local_markdown --tracker-path issues --backend mock
uv run republic doctor
uv run republic run --dry-run
uv run republic trigger 1
uv run republic dashboard
```

Repo-level demo script:

```bash
bash scripts/demo_local_markdown_tracker.sh
```
