# Example Local File Inbox

This sample repository demonstrates RepoAgents with the `local_file` tracker.

## Files

- `parser.py`: tiny parser module with an empty-input bug.
- `tests/test_parser.py`: minimal parser tests.
- `issues.json`: local issue inbox consumed by `tracker.kind: local_file`.

## Demo

```bash
uv run repoagents init --preset python-library --tracker-kind local_file --tracker-path issues.json --backend mock
uv run repoagents doctor
uv run repoagents run --dry-run
uv run repoagents trigger 1
uv run repoagents dashboard
```

Repo-level demo script:

```bash
bash scripts/demo_local_file_tracker.sh
```

For the same tracker with staged offline publish proposals and `sync apply`, see [examples/local-file-sync/README.md](../local-file-sync/README.md).
