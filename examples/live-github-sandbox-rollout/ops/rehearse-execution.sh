#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${REPOREPUBLIC_PROJECT_ROOT:-}"
REPORT_ROOT="${REPOREPUBLIC_SANDBOX_EXECUTION_REPORT_ROOT:-.ai-repoagents/reports/sandbox-execution}"
HANDOFF_DIR="${REPOREPUBLIC_EXECUTION_HANDOFF_OUTPUT_DIR:-.ai-repoagents/reports/ops/sandbox-issue-201}"
ISSUE_ID="${REPOREPUBLIC_SANDBOX_EXECUTION_ISSUE_ID:-201}"

run_republic() {
  if [[ -n "$PROJECT_ROOT" ]]; then
    uv run --project "$PROJECT_ROOT" repoagents "$@"
  else
    uv run repoagents "$@"
  fi
}

run_python() {
  if [[ -n "$PROJECT_ROOT" ]]; then
    uv run --project "$PROJECT_ROOT" python "$@"
  else
    uv run python "$@"
  fi
}

refresh_git_baseline() {
  local label="$1"
  git add .ai-repoagents/repoagents.yaml
  if git diff --cached --quiet -- .ai-repoagents/repoagents.yaml; then
    return
  fi
  git commit -q -m "$label"
}

mkdir -p "$REPORT_ROOT"
cp .ai-repoagents/repoagents.yaml "$REPORT_ROOT/repoagents.pre-execution.yaml"

run_python - <<'PY'
from pathlib import Path
import yaml

path = Path(".ai-repoagents/repoagents.yaml")
payload = yaml.safe_load(path.read_text(encoding="utf-8"))
payload["tracker"]["mode"] = "fixture"
payload["tracker"]["fixtures_path"] = "issues.json"
payload["tracker"]["path"] = "issues.json"
payload["tracker"]["smoke_fixture_path"] = None
path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
PY

refresh_git_baseline "sandbox execution mode"

run_republic trigger "$ISSUE_ID" --dry-run > "$REPORT_ROOT/trigger-dry-run.txt"
run_republic trigger "$ISSUE_ID" > "$REPORT_ROOT/trigger.txt"
run_republic status --issue "$ISSUE_ID" --format all --output "$REPORT_ROOT/status.json"
run_republic ops snapshot \
  --output-dir "$HANDOFF_DIR" \
  --include-sync-check \
  --include-sync-repair-preview \
  --archive

cp "$REPORT_ROOT/repoagents.pre-execution.yaml" .ai-repoagents/repoagents.yaml
refresh_git_baseline "sandbox execution restore live mode"

run_republic doctor --format all
run_republic github smoke --format all --require-write-ready
run_republic ops status --format all
run_republic dashboard --refresh-seconds 30 --format all

printf 'Sandbox execution reports: %s\n' "$REPORT_ROOT"
printf 'Execution handoff bundle: %s\n' "$HANDOFF_DIR"
printf 'Execution issue: %s\n' "$ISSUE_ID"
