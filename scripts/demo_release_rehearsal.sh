#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"
REPORT_ROOT_REL="${REPOREPUBLIC_RELEASE_REHEARSAL_REPORT_ROOT:-.ai-republic/reports/release-rehearsal}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reporepublic-release-rehearsal-XXXXXX")"
else
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
fi

tar \
  -C "$ROOT_DIR" \
  --exclude=".git" \
  --exclude=".venv" \
  --exclude=".pytest_cache" \
  --exclude="dist" \
  --exclude=".ai-republic/artifacts" \
  --exclude=".ai-republic/dashboard" \
  --exclude=".ai-republic/inbox" \
  --exclude=".ai-republic/logs" \
  --exclude=".ai-republic/reports" \
  --exclude=".ai-republic/state" \
  --exclude=".ai-republic/sync" \
  --exclude=".ai-republic/sync-applied" \
  --exclude=".ai-republic/workspaces" \
  -cf - . | tar -C "$DEST_DIR" -xf -

pushd "$DEST_DIR" >/dev/null

git init -q
git config user.name "RepoRepublic Demo"
git config user.email "demo@reporepublic.local"
git add .
git commit -q -m "initial release rehearsal snapshot"

mkdir -p "$REPORT_ROOT_REL"

uv run republic release preview --format all >"$REPORT_ROOT_REL/release-preview.stdout.txt"
uv run republic release announce --format all >"$REPORT_ROOT_REL/release-announce.stdout.txt"

TAG="$(
  uv run python - <<'PY'
from pathlib import Path
import json

payload = json.loads(Path(".ai-republic/reports/release-preview.json").read_text(encoding="utf-8"))
print(payload["target"]["tag"])
PY
)"

git tag -a "$TAG" -m "RepoRepublic ${TAG} rehearsal"
git tag -n99 "$TAG" >"$REPORT_ROOT_REL/tag.txt"
git show "$TAG" --stat >"$REPORT_ROOT_REL/tag-show.txt"

uv build >"$REPORT_ROOT_REL/build.txt"
if compgen -G "dist/*" >/dev/null; then
  shasum -a 256 dist/* >"$REPORT_ROOT_REL/dist.sha256.txt"
  ls -1 dist >"$REPORT_ROOT_REL/dist.files.txt"
fi

cat >"$REPORT_ROOT_REL/rehearsal-order.md" <<EOF
# Release Rehearsal Order

1. Open \`.ai-republic/reports/release-preview.md\`
2. Open \`.ai-republic/reports/release-announce.md\`
3. Copy \`.ai-republic/reports/release-cut-${TAG}.md\`
4. Inspect \`${REPORT_ROOT_REL}/tag.txt\` and \`${REPORT_ROOT_REL}/tag-show.txt\`
5. Inspect \`${REPORT_ROOT_REL}/dist.sha256.txt\`
EOF

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
printf 'Release rehearsal reports: %s\n' "$DEST_DIR/$REPORT_ROOT_REL"
printf 'Local rehearsal tag: %s\n' "$TAG"
