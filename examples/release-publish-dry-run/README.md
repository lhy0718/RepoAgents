# Example Release Publish Dry-Run

This example documents the local asset-publish dry-run path for RepoAgents.

## What it shows

- local version-bump rehearsal to the inferred preview target
- `repoagents release preview --format all`
- `repoagents release announce --format all`
- `repoagents release assets --build --smoke-install --format all`
- local annotated tag evidence plus built artifact checksums

## Demo

```bash
bash scripts/demo_release_publish_dry_run.sh
```

The demo copies the current repository into a temporary workspace, infers the next public-preview tag, patches the local version files to that target, creates a local annotated rehearsal tag, runs the release preview and announcement commands, then builds wheel/sdist artifacts and performs a local wheel install smoke test.

The generated dry-run artifacts include:

- `.ai-repoagents/reports/release-preview.json|md`
- `.ai-repoagents/reports/release-announce.json|md`
- `.ai-repoagents/reports/release-assets.json|md`
- `.ai-repoagents/reports/release-assets-v<tag>.md`
- `.ai-repoagents/reports/release-cut-v<tag>.md`
- `.ai-repoagents/reports/release-publish-dry-run/tag.txt`
- `.ai-repoagents/reports/release-publish-dry-run/tag-show.txt`
- `.ai-repoagents/reports/release-publish-dry-run/release-assets-summary.md`
- `.ai-repoagents/reports/release-publish-dry-run/publish-order.md`

## Suggested use

1. Run this after the release tag and announcement dry-run looks correct.
2. Check `release-assets.md` for artifact status and smoke-install posture.
3. Check `release-assets-v<tag>.md` before uploading assets to GitHub Releases or TestPyPI.
4. Use `release-cut-v<tag>.md` as the final command checklist.
