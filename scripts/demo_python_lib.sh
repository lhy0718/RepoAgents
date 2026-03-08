#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/examples/python-lib"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reporepublic-python-lib-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

cp -R "$SOURCE_DIR/." "$DEST_DIR/"

pushd "$DEST_DIR" >/dev/null

uv run --project "$ROOT_DIR" republic init \
  --preset python-library \
  --fixture-issues issues.json \
  --tracker-repo demo/python-lib

python3 - <<'PY'
from pathlib import Path

path = Path(".ai-republic/reporepublic.yaml")
body = path.read_text(encoding="utf-8")
path.write_text(body.replace("mode: codex", "mode: mock"), encoding="utf-8")
PY

uv run --project "$ROOT_DIR" republic doctor
uv run --project "$ROOT_DIR" republic run --dry-run
uv run --project "$ROOT_DIR" republic run --once
uv run --project "$ROOT_DIR" republic status
uv run --project "$ROOT_DIR" republic dashboard

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
