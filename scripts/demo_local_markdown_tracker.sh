#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/examples/local-markdown-inbox"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reporepublic-local-markdown-XXXXXX")"
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

uv run --project "$ROOT_DIR" republic doctor
uv run --project "$ROOT_DIR" republic run --dry-run
uv run --project "$ROOT_DIR" republic trigger 1
uv run --project "$ROOT_DIR" republic status
uv run --project "$ROOT_DIR" republic dashboard

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
