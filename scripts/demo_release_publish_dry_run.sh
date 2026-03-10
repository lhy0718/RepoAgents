#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${REPOREPUBLIC_DEMO_DEST:-}"
REPORT_ROOT_REL="${REPOREPUBLIC_RELEASE_PUBLISH_REPORT_ROOT:-.ai-republic/reports/release-publish-dry-run}"

if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/reporepublic-release-publish-XXXXXX")"
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
git commit -q -m "initial release publish dry-run snapshot"

mkdir -p "$REPORT_ROOT_REL"

uv run republic release preview --format all >"$REPORT_ROOT_REL/release-preview.stdout.txt"
TAG="$(
  uv run python - <<'PY'
from pathlib import Path
import json

payload = json.loads(Path(".ai-republic/reports/release-preview.json").read_text(encoding="utf-8"))
print(payload["target"]["tag"])
PY
)"
VERSION="${TAG#v}"

uv run python - <<'PY'
from pathlib import Path
import re
import tomllib

preview = Path(".ai-republic/reports/release-preview.json")
import json
target_version = json.loads(preview.read_text(encoding="utf-8"))["target"]["version"]

pyproject_path = Path("pyproject.toml")
pyproject_body = pyproject_path.read_text(encoding="utf-8")
pyproject_body = re.sub(r'(?m)^version = ".*"$', f'version = "{target_version}"', pyproject_body)
pyproject_path.write_text(pyproject_body, encoding="utf-8")

package_init_path = Path("src/reporepublic/__init__.py")
package_body = package_init_path.read_text(encoding="utf-8")
package_body = re.sub(r'__version__\s*=\s*".*"', f'__version__ = "{target_version}"', package_body)
package_init_path.write_text(package_body, encoding="utf-8")
PY

git add pyproject.toml src/reporepublic/__init__.py
if ! git diff --cached --quiet; then
  git commit -q -m "rehearse release publish version bump"
fi
git tag -a "$TAG" -m "RepoRepublic ${TAG} publish dry-run"

uv run republic release announce --format all >"$REPORT_ROOT_REL/release-announce.stdout.txt"
uv run republic release assets --build --smoke-install --format all >"$REPORT_ROOT_REL/release-assets.stdout.txt"

git tag -n99 "$TAG" >"$REPORT_ROOT_REL/tag.txt"
git show "$TAG" --stat >"$REPORT_ROOT_REL/tag-show.txt"
cp ".ai-republic/reports/release-assets-${TAG}.md" "$REPORT_ROOT_REL/release-assets-summary.md"

cat >"$REPORT_ROOT_REL/publish-order.md" <<EOF
# Release Publish Dry-Run Order

1. Open \`.ai-republic/reports/release-preview.md\`
2. Open \`.ai-republic/reports/release-announce.md\`
3. Open \`.ai-republic/reports/release-assets.md\`
4. Copy \`.ai-republic/reports/release-cut-${TAG}.md\`
5. Inspect \`${REPORT_ROOT_REL}/tag-show.txt\`
6. Inspect \`${REPORT_ROOT_REL}/release-assets-summary.md\`
EOF

popd >/dev/null

printf 'Demo workspace: %s\n' "$DEST_DIR"
printf 'Release publish dry-run reports: %s\n' "$DEST_DIR/$REPORT_ROOT_REL"
printf 'Rehearsal publish tag: %s\n' "$TAG"
