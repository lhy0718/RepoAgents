#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/examples/live-github-ops"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reporepublic-live-ops-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

cp -R "$SOURCE_DIR/." "$DEST_DIR/"

pushd "$DEST_DIR" >/dev/null

git init -q
git config user.name "RepoRepublic Demo"
git config user.email "demo@reporepublic.local"
git remote add origin git@github.com:acme/example-repo.git
git add .
git commit -q -m "initial"

uv run --project "$ROOT_DIR" republic init \
  --preset python-library \
  --tracker-repo acme/example-repo

uv run --project "$ROOT_DIR" python - <<'PY'
from pathlib import Path
import yaml

path = Path(".ai-republic/reporepublic.yaml")
payload = yaml.safe_load(path.read_text(encoding="utf-8"))
payload["tracker"]["kind"] = "github"
payload["tracker"]["repo"] = "acme/example-repo"
payload["tracker"]["mode"] = "rest"
payload["tracker"]["smoke_fixture_path"] = "ops/github-smoke.fixture.json"
payload["tracker"]["poll_interval_seconds"] = 300
payload["workspace"]["strategy"] = "worktree"
payload["workspace"]["dirty_policy"] = "block"
payload["logging"]["file_enabled"] = True
payload["logging"]["json"] = True
payload["safety"]["allow_write_comments"] = False
payload["safety"]["allow_open_pr"] = False
payload["llm"]["mode"] = "codex"
path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
PY

mkdir -p .ai-republic/logs

export GITHUB_TOKEN="demo-live-token"
uv run --project "$ROOT_DIR" republic github smoke --format all
REPOREPUBLIC_PROJECT_ROOT="$ROOT_DIR" \
REPOREPUBLIC_HANDOFF_OUTPUT_DIR=".ai-republic/reports/ops/live-handoff-demo" \
  bash ops/build-handoff.sh
uv run --project "$ROOT_DIR" republic ops status --format all
uv run --project "$ROOT_DIR" republic dashboard --refresh-seconds 30 --format all

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
