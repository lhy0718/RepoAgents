#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/examples/web-app"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/repoagents-web-app-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

cp -R "$SOURCE_DIR/." "$DEST_DIR/"

pushd "$DEST_DIR" >/dev/null

uv run --project "$ROOT_DIR" repoagents init \
  --preset web-app \
  --fixture-issues issues.json \
  --tracker-repo demo/web-app

python3 - <<'PY'
from pathlib import Path

path = Path(".ai-repoagents/repoagents.yaml")
body = path.read_text(encoding="utf-8")
path.write_text(body.replace("mode: codex", "mode: mock"), encoding="utf-8")
PY

uv run --project "$ROOT_DIR" repoagents doctor
uv run --project "$ROOT_DIR" repoagents run --dry-run
uv run --project "$ROOT_DIR" repoagents run --once
uv run --project "$ROOT_DIR" repoagents status
uv run --project "$ROOT_DIR" repoagents dashboard

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
