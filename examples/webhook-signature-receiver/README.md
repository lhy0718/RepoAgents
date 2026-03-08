# Example Signed Webhook Receiver

This sample repository demonstrates a local HTTP receiver that validates GitHub-style webhook signatures before forwarding payloads into `republic webhook`.

## What it shows

- local POST handling at `/github`
- HMAC SHA-256 verification through `X-Hub-Signature-256`
- payload capture under `.ai-republic/inbox/webhooks/` only after signature verification
- forwarding into the existing `republic webhook` command after the request is authenticated

## Files

- `parser.py`: tiny parser module with an empty-input bug
- `tests/test_parser.py`: minimal parser tests
- `issues.json`: local issue inbox used by `tracker.kind: local_file`
- `payloads/issues-opened.json`: sample GitHub `issues` event payload

## Demo

```bash
bash scripts/demo_webhook_signature_receiver.sh
```

Equivalent manual flow:

```bash
uv run republic init --preset python-library --tracker-kind local_file --tracker-path issues.json --backend mock
export REPOREPUBLIC_WEBHOOK_SECRET=reporepublic-demo-secret
uv run --project /path/to/RepoRepublic python /path/to/RepoRepublic/scripts/webhook_receiver.py \
  --repo-root "$PWD" \
  --project-root /path/to/RepoRepublic \
  --render-dashboard \
  --secret-env REPOREPUBLIC_WEBHOOK_SECRET
```

Send a signed payload:

```bash
python - <<'PY'
import hashlib
import hmac
from pathlib import Path

import httpx

secret = "reporepublic-demo-secret"
body = Path("payloads/issues-opened.json").read_bytes()
signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
response = httpx.post(
    "http://127.0.0.1:8787/github",
    headers={
        "Content-Type": "application/json",
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": signature,
    },
    content=body,
    timeout=10.0,
)
response.raise_for_status()
print(response.text)
PY
```

After the POST completes, inspect:

- `.ai-republic/inbox/webhooks/`
- `.ai-republic/state/runs.json`
- `.ai-republic/dashboard/index.html`
