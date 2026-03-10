#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/demo_codex.sh"
SOURCE_DIR="$ROOT_DIR/examples/docs-maintainer-pack"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/repoagents-docs-maintainer-pack-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

cp -R "$SOURCE_DIR/." "$DEST_DIR/"

pushd "$DEST_DIR" >/dev/null

uv run --project "$ROOT_DIR" repoagents init \
  --preset docs-only \
  --fixture-issues issues.json \
  --tracker-repo demo/docs-maintainer-pack

configure_demo_codex "$ROOT_DIR" "$DEST_DIR"

cp -R pack/roles/. .ai-repoagents/roles/
cp -R pack/prompts/. .ai-repoagents/prompts/
cp -R pack/policies/. .ai-repoagents/policies/
cat pack/AGENTS.append.md >> AGENTS.md

uv run --project "$ROOT_DIR" repoagents doctor
uv run --project "$ROOT_DIR" repoagents trigger 1
uv run --project "$ROOT_DIR" repoagents status --issue 1
uv run --project "$ROOT_DIR" repoagents dashboard

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
