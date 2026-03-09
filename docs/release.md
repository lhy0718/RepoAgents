# Release Checklist

This guide is for maintainers preparing a public RepoRepublic release.

## One-command preflight

Use the consolidated preflight when you want one command that runs the release checklist and leaves every artifact you need for the tag cut:

```bash
uv run republic release check --format all
bash scripts/release_preflight.sh
```

By default, `republic release check` runs the full preflight:

- release preview target inference
- release announcement copy pack generation
- `uv run pytest -q`
- `uv build`
- temporary-wheel smoke install for `republic --help`
- open-source governance and CI file presence checks

It exports:

- `.ai-republic/reports/release-checklist.json`
- `.ai-republic/reports/release-checklist.md`
- `.ai-republic/reports/release-preview.json`
- `.ai-republic/reports/release-announce.json`
- `.ai-republic/reports/release-assets.json`

The command exits with code `0` only when the repository is ready to publish. Any blocking issue or follow-up item keeps the exit code non-zero so you can use it as the last local gate before tagging.

## Release dry-run

Use the built-in preview before you touch tags:

```bash
uv run republic release preview
uv run republic release preview --format all
uv run republic release announce --format all
uv run republic release check --format all
```

The preview works even if the repository has not been bootstrapped with `republic init`.

It produces:

- `.ai-republic/reports/release-preview.json`
- `.ai-republic/reports/release-preview.md`
- `.ai-republic/reports/release-notes-v<version>.md`
- `.ai-republic/reports/release-announce.json`
- `.ai-republic/reports/release-announce.md`
- `.ai-republic/reports/announcement-v<version>.md`
- `.ai-republic/reports/discussion-v<version>.md`
- `.ai-republic/reports/social-v<version>.md`
- `.ai-republic/reports/release-cut-v<version>.md`

The preview checks:

- `pyproject.toml` and `src/reporepublic/__init__.py` version alignment
- whether `CHANGELOG.md` still has usable `Unreleased` notes
- whether the inferred or requested target tag already exists in the changelog
- current branch and working-tree cleanliness

If the current project version already has a dated changelog section and `Unreleased` still contains notes, RepoRepublic infers the next patch tag for the preview. For example, `0.1.0` plus new `Unreleased` notes previews `v0.1.1`.

## Announcement copy pack

`republic release announce --format all` reuses the same inferred target tag and writes a copy pack for maintainers:

- short public announcement
- pinned discussion draft
- short social copy
- release-cut checklist
- GitHub release notes markdown

Use this when you want one place to copy the release message set instead of assembling each post by hand.

If you want a full disposable rehearsal, run:

```bash
bash scripts/demo_release_rehearsal.sh
```

That script copies the current repository into a temporary workspace, generates preview/announcement artifacts, creates a local annotated rehearsal tag, runs `uv build`, and records tag/build evidence under `.ai-republic/reports/release-rehearsal/`.

## Asset publish dry-run

Use the asset report when you want to validate wheel/sdist output and the post-tag upload commands without touching an external package index:

```bash
uv run republic release assets --format all
uv run republic release assets --build --smoke-install --format all
```

This exports:

- `.ai-republic/reports/release-assets.json`
- `.ai-republic/reports/release-assets.md`
- `.ai-republic/reports/release-assets-v<tag>.md`

The asset report captures:

- wheel/sdist presence
- artifact size and sha256
- target-version alignment
- optional `uv build` result
- optional wheel install smoke via a temporary venv
- suggested `gh release upload` and `twine upload` commands

For a disposable end-to-end rehearsal, run:

```bash
bash scripts/demo_release_publish_dry_run.sh
```

That script patches the copied workspace to the inferred preview version, creates a local annotated rehearsal tag, runs `republic release assets --build --smoke-install --format all`, and records tag/build evidence under `.ai-republic/reports/release-publish-dry-run/`.

## Before you cut a release

1. Confirm the working tree is clean.
2. Confirm the changelog is updated.
3. Confirm README, quickstart, and docs index links still match the current surface.
4. Confirm major examples still run.

## Local verification

Run from the repository root:

```bash
uv sync --dev
uv run pytest -q
uv build
```

Optional but recommended install smoke:

```bash
python3.12 -m venv /tmp/reporepublic-release-smoke
/tmp/reporepublic-release-smoke/bin/pip install dist/*.whl
/tmp/reporepublic-release-smoke/bin/republic --help
```

If you changed live GitHub or Codex surfaces, also consider the opt-in smoke paths:

```bash
CODEX_E2E=1 uv run pytest tests/test_codex_backend.py -k live_smoke -rs
GITHUB_E2E=1 REPOREPUBLIC_GITHUB_TEST_REPO=owner/name uv run pytest tests/test_tracker.py -k live_read_only -rs
```

Only run write-path live GitHub checks against a dedicated sandbox repo.

## Release notes content

Make sure the release notes cover:

- headline user-visible features
- safety or policy changes
- migration or config notes
- known limitations that still apply

## Tagging and publishing

1. Bump `version` in [pyproject.toml](../pyproject.toml).
2. Move release notes from `Unreleased` to a dated version section in [CHANGELOG.md](../CHANGELOG.md).
3. Commit the release prep.
4. Create an annotated tag, for example `v0.1.1`.
5. Push `main` and the tag.
6. Create the GitHub release using the changelog notes.
7. If you are publishing to PyPI, publish only after CI for the tagged commit is green.

The preview exports a ready-to-copy GitHub release body file. The default publish command is:

```bash
gh release create v0.1.1 --title "RepoRepublic v0.1.1" --notes-file .ai-republic/reports/release-notes-v0.1.1.md
```

## After release

- verify install and `republic --help` from the released artifact
- verify docs links in the GitHub release description
- update any roadmap or backlog notes that changed because of the release
