#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/demo_codex.sh"
SOURCE_DIR="$ROOT_DIR/examples/local-file-sync"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/repoagents-local-file-sync-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

cp -R "$SOURCE_DIR/." "$DEST_DIR/"

pushd "$DEST_DIR" >/dev/null

uv run --project "$ROOT_DIR" repoagents init \
  --preset python-library \
  --tracker-kind local_file \
  --tracker-path issues.json

configure_demo_codex "$ROOT_DIR" "$DEST_DIR"

uv run --project "$ROOT_DIR" repoagents doctor
uv run --project "$ROOT_DIR" repoagents run --dry-run
uv run --project "$ROOT_DIR" repoagents trigger 1
uv run --project "$ROOT_DIR" repoagents status --issue 1
uv run --project "$ROOT_DIR" repoagents sync ls --issue 1
uv run --project "$ROOT_DIR" repoagents sync apply --issue 1 --tracker local-file --action comment --latest
uv run --project "$ROOT_DIR" repoagents sync ls --scope applied --issue 1
uv run --project "$ROOT_DIR" repoagents dashboard

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
