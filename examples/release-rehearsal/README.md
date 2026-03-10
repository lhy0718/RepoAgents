# Example Release Rehearsal

This example documents the local public-preview tag rehearsal path for RepoAgents itself.

## What it shows

- `repoagents release preview --format all`
- `repoagents release announce --format all`
- local annotated tag creation in a disposable clone
- build artifact generation plus checksum capture
- a fixed read order for the release-cut artifacts

## Demo

```bash
bash scripts/demo_release_rehearsal.sh
```

The demo copies the current repository into a temporary workspace, initializes a fresh local git history, generates release preview and announcement artifacts, creates a local annotated rehearsal tag, runs `uv build`, and records the resulting tag/build evidence under `.ai-repoagents/reports/release-rehearsal/`.

The generated rehearsal artifacts include:

- `.ai-repoagents/reports/release-preview.json|md`
- `.ai-repoagents/reports/release-announce.json|md`
- `.ai-repoagents/reports/announcement-v<version>.md`
- `.ai-repoagents/reports/discussion-v<version>.md`
- `.ai-repoagents/reports/social-v<version>.md`
- `.ai-repoagents/reports/release-cut-v<version>.md`
- `.ai-repoagents/reports/release-rehearsal/tag.txt`
- `.ai-repoagents/reports/release-rehearsal/tag-show.txt`
- `.ai-repoagents/reports/release-rehearsal/build.txt`
- `.ai-repoagents/reports/release-rehearsal/dist.sha256.txt`
- `.ai-repoagents/reports/release-rehearsal/rehearsal-order.md`

## Suggested use

1. Run the rehearsal before the real public-preview tag cut.
2. Read `release-preview.md` first.
3. Read `release-announce.md` second.
4. Copy `release-cut-v<version>.md` when you are ready to run the actual commands.
5. Check `tag-show.txt` and `dist.sha256.txt` before tagging the real repository.
