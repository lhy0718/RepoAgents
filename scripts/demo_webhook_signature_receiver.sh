#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/examples/webhook-signature-receiver"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"
PORT="${REPOREPUBLIC_WEBHOOK_PORT:-8788}"
SECRET="${REPOREPUBLIC_WEBHOOK_SECRET:-reporepublic-demo-secret}"
SERVER_LOG=""
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reporepublic-webhook-signature-receiver-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

cp -R "$SOURCE_DIR/." "$DEST_DIR/"
SERVER_LOG="$DEST_DIR/webhook-receiver.log"

pushd "$DEST_DIR" >/dev/null

uv run --project "$ROOT_DIR" republic init \
  --preset python-library \
  --tracker-kind local_file \
  --tracker-path issues.json \
  --backend mock

export REPOREPUBLIC_WEBHOOK_SECRET="$SECRET"
uv run --project "$ROOT_DIR" python "$ROOT_DIR/scripts/webhook_receiver.py" \
  --repo-root "$DEST_DIR" \
  --project-root "$ROOT_DIR" \
  --host 127.0.0.1 \
  --port "$PORT" \
  --render-dashboard \
  --secret-env REPOREPUBLIC_WEBHOOK_SECRET \
  --max-requests 1 \
  >"$SERVER_LOG" 2>&1 &
SERVER_PID="$!"

uv run --project "$ROOT_DIR" python - <<'PY' "$PORT"
import socket
import sys
import time

port = int(sys.argv[1])
deadline = time.time() + 10
while time.time() < deadline:
    with socket.socket() as sock:
        sock.settimeout(0.25)
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(0)
    time.sleep(0.1)
raise SystemExit("webhook receiver did not become ready in time")
PY

uv run --project "$ROOT_DIR" python - <<'PY' "$PORT" "$DEST_DIR/payloads/issues-opened.json" "$SECRET"
import hashlib
import hmac
import sys

import httpx

port = int(sys.argv[1])
payload_path = sys.argv[2]
secret = sys.argv[3]
payload = open(payload_path, "rb").read()
signature = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
response = httpx.post(
    f"http://127.0.0.1:{port}/github",
    headers={
        "Content-Type": "application/json",
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": signature,
    },
    content=payload,
    timeout=10.0,
)
response.raise_for_status()
print(response.text)
PY

wait "$SERVER_PID"
SERVER_PID=""

uv run --project "$ROOT_DIR" republic status --issue 1

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
