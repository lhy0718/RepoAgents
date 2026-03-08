# Example Webhook Receiver

This sample repository demonstrates a minimal local HTTP receiver that forwards GitHub-style webhook payloads into `republic webhook`.

## What it shows

- local POST handling at `/github`
- payload capture under `.ai-republic/inbox/webhooks/`
- forwarding into the existing `republic webhook` command
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
uv run republic init --preset python-library --tracker-kind local_file --tracker-path issues.json --backend mock
uv run --project /path/to/RepoRepublic python /path/to/RepoRepublic/scripts/webhook_receiver.py --repo-root "$PWD" --project-root /path/to/RepoRepublic --render-dashboard
curl -X POST http://127.0.0.1:8787/github \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Event: issues' \
  --data @payloads/issues-opened.json
```

After the POST completes, inspect:

- `.ai-republic/inbox/webhooks/`
- `.ai-republic/state/runs.json`
- `.ai-republic/dashboard/index.html`

For the signed variant with `X-Hub-Signature-256` verification, see [../webhook-signature-receiver/README.md](../webhook-signature-receiver/README.md).
