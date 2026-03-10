#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${REPOREPUBLIC_PROJECT_ROOT:-}"
REPORT_ROOT="${REPOREPUBLIC_SANDBOX_REPORT_ROOT:-.ai-repoagents/reports/sandbox-rollout}"
HANDOFF_DIR="${REPOREPUBLIC_HANDOFF_OUTPUT_DIR:-.ai-repoagents/reports/ops/sandbox-pr-ready}"

run_republic() {
  if [[ -n "$PROJECT_ROOT" ]]; then
    uv run --project "$PROJECT_ROOT" repoagents "$@"
  else
    uv run repoagents "$@"
  fi
}

set_phase() {
  if [[ -n "$PROJECT_ROOT" ]]; then
    REPOREPUBLIC_PROJECT_ROOT="$PROJECT_ROOT" bash ops/set-sandbox-phase.sh "$1"
  else
    bash ops/set-sandbox-phase.sh "$1"
  fi
}

refresh_git_baseline() {
  local phase="$1"
  git add .ai-repoagents/repoagents.yaml
  if git diff --cached --quiet -- .ai-repoagents/repoagents.yaml; then
    return
  fi
  git commit -q -m "sandbox phase: $phase"
}

run_phase_reports() {
  local phase="$1"
  local phase_dir="$REPORT_ROOT/$phase"
  local smoke_exit=0
  local expected_exit=0

  mkdir -p "$phase_dir"
  set_phase "$phase"
  refresh_git_baseline "$phase"
  run_republic doctor --format all --output "$phase_dir/doctor.json"

  if [[ "$phase" == "pr-gated" || "$phase" == "pr-ready" ]]; then
    if [[ "$phase" == "pr-gated" ]]; then
      expected_exit=1
    fi
    set +e
    run_republic github smoke \
      --format all \
      --output "$phase_dir/github-smoke.json" \
      --require-write-ready
    smoke_exit=$?
    set -e
    printf '%s\n' "$smoke_exit" > "$phase_dir/require-write-ready.exit-code"
    if [[ "$smoke_exit" -ne "$expected_exit" ]]; then
      printf 'Unexpected --require-write-ready exit for %s: got %s expected %s\n' \
        "$phase" "$smoke_exit" "$expected_exit" >&2
      exit 1
    fi
    return
  fi

  run_republic github smoke --format all --output "$phase_dir/github-smoke.json"
}

mkdir -p "$REPORT_ROOT"

for phase in baseline comments-ready pr-gated pr-ready; do
  run_phase_reports "$phase"
done

run_republic doctor --format all
run_republic github smoke --format all --require-write-ready
run_republic ops snapshot \
  --output-dir "$HANDOFF_DIR" \
  --include-sync-check \
  --include-sync-repair-preview \
  --archive
run_republic ops status --format all
run_republic dashboard --refresh-seconds 30 --format all

printf 'Sandbox rollout reports: %s\n' "$REPORT_ROOT"
printf 'Final handoff bundle: %s\n' "$HANDOFF_DIR"
printf 'Rollout order: %s\n' "baseline -> comments-ready -> pr-gated -> pr-ready"
printf 'Open order: %s\n' "baseline smoke -> comments-ready smoke -> pr-gated gate -> pr-ready gate -> handoff bundle -> dashboard"
