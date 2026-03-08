#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/examples/docs-maintainer-pack"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reporepublic-docs-maintainer-pack-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

cp -R "$SOURCE_DIR/." "$DEST_DIR/"

pushd "$DEST_DIR" >/dev/null

uv run --project "$ROOT_DIR" republic init \
  --preset docs-only \
  --fixture-issues issues.json \
  --tracker-repo demo/docs-maintainer-pack \
  --backend mock

cp -R pack/roles/. .ai-republic/roles/
cp -R pack/prompts/. .ai-republic/prompts/
cp -R pack/policies/. .ai-republic/policies/
cat pack/AGENTS.append.md >> AGENTS.md

uv run --project "$ROOT_DIR" republic doctor
uv run --project "$ROOT_DIR" republic trigger 1
uv run --project "$ROOT_DIR" republic status --issue 1
uv run --project "$ROOT_DIR" republic dashboard

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
