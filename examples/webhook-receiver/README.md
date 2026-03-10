# Example Webhook Receiver

This sample repository demonstrates a minimal local HTTP receiver that forwards GitHub-style webhook payloads into `repoagents webhook`.

## What it shows

- local POST handling at `/github`
- payload capture under `.ai-repoagents/inbox/webhooks/`
- forwarding into the existing `repoagents webhook` command
- optional dashboard regeneration after each accepted payload

## Files

- `parser.py`: tiny parser module with an empty-input bug.
- `tests/test_parser.py`: minimal parser tests.
- `issues.json`: local issue inbox used by `tracker.kind: local_file`.
- `payloads/issues-opened.json`: sample GitHub `issues` event payload.

## Demo

```bash
bash scripts/demo_webhook_receiver.sh
```

Equivalent manual flow:

```bash
uv run repoagents init --preset python-library --tracker-kind local_file --tracker-path issues.json
uv run --project /path/to/RepoAgents python /path/to/RepoAgents/scripts/webhook_receiver.py --repo-root "$PWD" --project-root /path/to/RepoAgents --render-dashboard
curl -X POST http://127.0.0.1:8787/github \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Event: issues' \
  --data @payloads/issues-opened.json
```

Use the repo-level demo script when you want the offline shim configured automatically.

After the POST completes, inspect:

- `.ai-repoagents/inbox/webhooks/`
- `.ai-repoagents/state/runs.json`
- `.ai-repoagents/dashboard/index.html`

For the signed variant with `X-Hub-Signature-256` verification, see [../webhook-signature-receiver/README.md](../webhook-signature-receiver/README.md).
