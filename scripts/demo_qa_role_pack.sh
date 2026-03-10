#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/demo_codex.sh"
SOURCE_DIR="$ROOT_DIR/examples/qa-role-pack"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/repoagents-qa-role-pack-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

cp -R "$SOURCE_DIR/." "$DEST_DIR/"

pushd "$DEST_DIR" >/dev/null

uv run --project "$ROOT_DIR" repoagents init \
  --preset python-library \
  --fixture-issues issues.json \
  --tracker-repo demo/qa-role-pack

configure_demo_codex "$ROOT_DIR" "$DEST_DIR"

uv run --project "$ROOT_DIR" python - <<'PY'
from pathlib import Path
import yaml

path = Path(".ai-repoagents/repoagents.yaml")
payload = yaml.safe_load(path.read_text(encoding="utf-8"))
payload["roles"]["enabled"] = ["triage", "planner", "engineer", "qa", "reviewer"]
path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
PY

uv run --project "$ROOT_DIR" repoagents doctor
uv run --project "$ROOT_DIR" repoagents trigger 1
uv run --project "$ROOT_DIR" repoagents status --issue 1
uv run --project "$ROOT_DIR" repoagents dashboard

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
