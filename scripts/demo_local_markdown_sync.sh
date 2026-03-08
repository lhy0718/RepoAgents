#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/examples/local-markdown-sync"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reporepublic-local-markdown-sync-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

cp -R "$SOURCE_DIR/." "$DEST_DIR/"

pushd "$DEST_DIR" >/dev/null

uv run --project "$ROOT_DIR" republic init \
  --preset python-library \
  --tracker-kind local_markdown \
  --tracker-path issues \
  --backend mock

uv run --project "$ROOT_DIR" python - <<'PY'
from pathlib import Path

path = Path(".ai-republic/reporepublic.yaml")
body = path.read_text(encoding="utf-8")
body = body.replace("allow_open_pr: false", "allow_open_pr: true")
path.write_text(body, encoding="utf-8")
PY

uv run --project "$ROOT_DIR" republic doctor
uv run --project "$ROOT_DIR" republic run --dry-run
uv run --project "$ROOT_DIR" republic trigger 1
uv run --project "$ROOT_DIR" republic status --issue 1
uv run --project "$ROOT_DIR" republic sync ls --issue 1
uv run --project "$ROOT_DIR" republic sync apply --issue 1 --tracker local-markdown --action comment --latest
uv run --project "$ROOT_DIR" republic sync apply --issue 1 --tracker local-markdown --action pr-body --latest --bundle
uv run --project "$ROOT_DIR" republic sync ls --scope applied --issue 1
uv run --project "$ROOT_DIR" republic dashboard

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
