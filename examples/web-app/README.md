# Example Web App

This sample repository is meant for RepoRepublic demos targeting a lightweight web app.

## Files

- `src/app.js`: minimal UI code.
- `issues.json`: sample GitHub issue fixtures for local dry-runs.

## Demo

```bash
uv run republic init --preset web-app --fixture-issues issues.json --tracker-repo demo/web-app
uv run republic run --dry-run
```

Repo-level demo script:

```bash
bash scripts/demo_web_app.sh
```
