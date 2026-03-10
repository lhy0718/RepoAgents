#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/demo_codex.sh"
SOURCE_DIR="$ROOT_DIR/examples/live-github-sandbox-rollout"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/repoagents-live-sandbox-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

cp -R "$SOURCE_DIR/." "$DEST_DIR/"

pushd "$DEST_DIR" >/dev/null

ensure_demo_codex() {
  install_demo_codex_command "$ROOT_DIR" "$DEST_DIR/.demo-bin/codex"
}

DEMO_CODEX_COMMAND="$(ensure_demo_codex)"

git init -q
git config user.name "RepoAgents Demo"
git config user.email "demo@repoagents.local"
git remote add origin git@github.com:acme/sandbox-repo.git
git add .
git commit -q -m "initial"

uv run --project "$ROOT_DIR" repoagents init \
  --preset python-library \
  --tracker-repo acme/sandbox-repo

REPOAGENTS_DEMO_CODEX_COMMAND="$DEMO_CODEX_COMMAND" uv run --project "$ROOT_DIR" python - <<'PY'
import os
from pathlib import Path
import yaml

path = Path(".ai-repoagents/repoagents.yaml")
payload = yaml.safe_load(path.read_text(encoding="utf-8"))
payload["tracker"]["kind"] = "github"
payload["tracker"]["repo"] = "acme/sandbox-repo"
payload["tracker"]["mode"] = "rest"
payload["tracker"]["smoke_fixture_path"] = "ops/github-smoke.baseline.json"
payload["tracker"]["poll_interval_seconds"] = 300
payload["workspace"]["strategy"] = "worktree"
payload["workspace"]["dirty_policy"] = "block"
payload["logging"]["file_enabled"] = True
payload["logging"]["json"] = True
payload["safety"]["allow_write_comments"] = False
payload["safety"]["allow_open_pr"] = False
payload["llm"]["mode"] = "codex"
payload["codex"]["command"] = os.environ["REPOAGENTS_DEMO_CODEX_COMMAND"]
path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
PY

git add .
git commit -q -m "install repoagents sandbox rollout"

mkdir -p .ai-repoagents/logs

export GITHUB_TOKEN="demo-sandbox-token"
REPOREPUBLIC_PROJECT_ROOT="$ROOT_DIR" \
REPOREPUBLIC_SANDBOX_REPORT_ROOT=".ai-repoagents/reports/sandbox-rollout" \
REPOREPUBLIC_HANDOFF_OUTPUT_DIR=".ai-repoagents/reports/ops/sandbox-pr-ready" \
  bash ops/rehearse-rollout.sh
REPOREPUBLIC_PROJECT_ROOT="$ROOT_DIR" \
REPOREPUBLIC_SANDBOX_EXECUTION_REPORT_ROOT=".ai-repoagents/reports/sandbox-execution" \
REPOREPUBLIC_EXECUTION_HANDOFF_OUTPUT_DIR=".ai-repoagents/reports/ops/sandbox-issue-201" \
  bash ops/rehearse-execution.sh

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
