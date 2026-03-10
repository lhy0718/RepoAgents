# Example Local Markdown Inbox

This sample repository demonstrates RepoAgents with the `local_markdown` tracker.

## Files

- `parser.py`: tiny parser module with an empty-input bug.
- `tests/test_parser.py`: minimal parser tests.
- `issues/`: Markdown issue inbox consumed by `tracker.kind: local_markdown`.

## Demo

```bash
uv run repoagents init --preset python-library --tracker-kind local_markdown --tracker-path issues --backend mock
uv run repoagents doctor
uv run repoagents run --dry-run
uv run repoagents trigger 1
uv run repoagents dashboard
```

Repo-level demo script:

```bash
bash scripts/demo_local_markdown_tracker.sh
```
