#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${REPOREPUBLIC_PROJECT_ROOT:-}"
HANDOFF_DIR="${REPOREPUBLIC_HANDOFF_OUTPUT_DIR:-.ai-repoagents/reports/ops/live-handoff-demo}"

run_republic() {
  if [[ -n "$PROJECT_ROOT" ]]; then
    uv run --project "$PROJECT_ROOT" repoagents "$@"
  else
    uv run repoagents "$@"
  fi
}

run_republic github smoke --format all
ops_snapshot_exit=0
if ! run_republic ops snapshot \
  --output-dir "$HANDOFF_DIR" \
  --include-sync-check \
  --include-sync-repair-preview \
  --archive; then
  ops_snapshot_exit=$?
fi
run_republic ops status --format all

printf 'Handoff bundle: %s\n' "$HANDOFF_DIR"
printf 'Open order: %s\n' "index.html -> ops-brief.md -> github-smoke.md -> ops-status.md -> dashboard.html"
if [[ "$ops_snapshot_exit" -ne 0 ]]; then
  printf 'Note: ops snapshot exited with status %s because the rehearsal bundle still contains follow-up findings.\n' "$ops_snapshot_exit"
fi
