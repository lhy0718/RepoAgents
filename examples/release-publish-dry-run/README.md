# Example Release Publish Dry-Run

This example documents the local asset-publish dry-run path for RepoRepublic.

## What it shows

- local version-bump rehearsal to the inferred preview target
- `republic release preview --format all`
- `republic release announce --format all`
- `republic release assets --build --smoke-install --format all`
- local annotated tag evidence plus built artifact checksums

## Demo

```bash
bash scripts/demo_release_publish_dry_run.sh
```

The demo copies the current repository into a temporary workspace, infers the next public-preview tag, patches the local version files to that target, creates a local annotated rehearsal tag, runs the release preview and announcement commands, then builds wheel/sdist artifacts and performs a local wheel install smoke test.

The generated dry-run artifacts include:

- `.ai-republic/reports/release-preview.json|md`
- `.ai-republic/reports/release-announce.json|md`
- `.ai-republic/reports/release-assets.json|md`
- `.ai-republic/reports/release-assets-v<tag>.md`
- `.ai-republic/reports/release-cut-v<tag>.md`
- `.ai-republic/reports/release-publish-dry-run/tag.txt`
- `.ai-republic/reports/release-publish-dry-run/tag-show.txt`
- `.ai-republic/reports/release-publish-dry-run/release-assets-summary.md`
- `.ai-republic/reports/release-publish-dry-run/publish-order.md`

## Suggested use

1. Run this after the release tag and announcement dry-run looks correct.
2. Check `release-assets.md` for artifact status and smoke-install posture.
3. Check `release-assets-v<tag>.md` before uploading assets to GitHub Releases or TestPyPI.
4. Use `release-cut-v<tag>.md` as the final command checklist.
