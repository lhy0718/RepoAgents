# Example Python Library

This sample repository is meant for RepoAgents demos.

## Files

- `parser.py`: tiny parser module with an empty-input bug.
- `tests/test_parser.py`: minimal tests.
- `issues.json`: sample GitHub issue fixtures for local dry-runs.

## Demo

```bash
uv run repoagents init --preset python-library --fixture-issues issues.json --tracker-repo demo/python-lib
uv run repoagents run --dry-run
```

Repo-level demo script:

```bash
bash scripts/demo_python_lib.sh
```
