#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${REPOREPUBLIC_PROJECT_ROOT:-}"
PHASE="${1:-}"

run_python() {
  if [[ -n "$PROJECT_ROOT" ]]; then
    uv run --project "$PROJECT_ROOT" python "$@"
  else
    uv run python "$@"
  fi
}

if [[ -z "$PHASE" ]]; then
  printf 'Usage: %s <baseline|comments-ready|pr-gated|pr-ready>\n' "$0" >&2
  exit 1
fi

case "$PHASE" in
  baseline)
    FIXTURE_PATH="ops/github-smoke.baseline.json"
    ALLOW_COMMENTS="false"
    ALLOW_OPEN_PR="false"
    ;;
  comments-ready)
    FIXTURE_PATH="ops/github-smoke.comments-ready.json"
    ALLOW_COMMENTS="true"
    ALLOW_OPEN_PR="false"
    ;;
  pr-gated)
    FIXTURE_PATH="ops/github-smoke.pr-gated.json"
    ALLOW_COMMENTS="true"
    ALLOW_OPEN_PR="true"
    ;;
  pr-ready)
    FIXTURE_PATH="ops/github-smoke.pr-ready.json"
    ALLOW_COMMENTS="true"
    ALLOW_OPEN_PR="true"
    ;;
  *)
    printf 'Unknown sandbox phase: %s\n' "$PHASE" >&2
    exit 1
    ;;
esac

export REPOREPUBLIC_SANDBOX_PHASE="$PHASE"
export REPOREPUBLIC_SANDBOX_FIXTURE_PATH="$FIXTURE_PATH"
export REPOREPUBLIC_SANDBOX_ALLOW_COMMENTS="$ALLOW_COMMENTS"
export REPOREPUBLIC_SANDBOX_ALLOW_OPEN_PR="$ALLOW_OPEN_PR"

run_python - <<'PY'
from pathlib import Path
import os
import yaml

path = Path(".ai-repoagents/repoagents.yaml")
payload = yaml.safe_load(path.read_text(encoding="utf-8"))
payload["tracker"]["smoke_fixture_path"] = os.environ["REPOREPUBLIC_SANDBOX_FIXTURE_PATH"]
payload["safety"]["allow_write_comments"] = os.environ["REPOREPUBLIC_SANDBOX_ALLOW_COMMENTS"] == "true"
payload["safety"]["allow_open_pr"] = os.environ["REPOREPUBLIC_SANDBOX_ALLOW_OPEN_PR"] == "true"
path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
print(
    "Sandbox phase updated: "
    f"{os.environ['REPOREPUBLIC_SANDBOX_PHASE']} "
    f"(fixture={os.environ['REPOREPUBLIC_SANDBOX_FIXTURE_PATH']}, "
    f"allow_write_comments={os.environ['REPOREPUBLIC_SANDBOX_ALLOW_COMMENTS']}, "
    f"allow_open_pr={os.environ['REPOREPUBLIC_SANDBOX_ALLOW_OPEN_PR']})"
)
PY
