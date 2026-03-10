#!/usr/bin/env bash
set -euo pipefail

install_demo_codex_command() {
  local root_dir="$1"
  local target_path="$2"

  uv run --project "$root_dir" python -m repoagents.testing.fake_codex \
    --install-shim "$target_path" \
    --project-root "$root_dir"
}

configure_demo_codex() {
  local root_dir="$1"
  local workspace_dir="$2"
  local command_path="${3:-$workspace_dir/.demo-bin/codex}"

  command_path="$(install_demo_codex_command "$root_dir" "$command_path")"
  REPOAGENTS_DEMO_CODEX_COMMAND="$command_path" uv run --project "$root_dir" python - <<'PY'
import os
from pathlib import Path
import yaml

path = Path(".ai-repoagents/repoagents.yaml")
payload = yaml.safe_load(path.read_text(encoding="utf-8"))
payload.setdefault("codex", {})["command"] = os.environ["REPOAGENTS_DEMO_CODEX_COMMAND"]
path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
PY
}
