# Sync Artifacts

RepoRepublic uses `.ai-republic/sync/` as a tracker-agnostic staging area for publish actions that should not be applied directly to an external system.

## Why it exists

Use sync artifacts when:

- a tracker is intentionally offline
- a repo wants human-controlled handoff before comments or PRs are applied
- you need deterministic local review of proposed external writes

## Layout contract

```text
.ai-republic/sync/
  <tracker>/
    issue-<id>/
      <timestamp>-<action>.json
      <timestamp>-<action>.md
```

Current built-in writer:

- `local-file`
- `local-markdown`

Current built-in apply helper:

- `local-file`
- `local-markdown`

Implementation note:

- built-in sync apply behavior is registered through `SyncActionRegistry` in [src/reporepublic/sync_artifacts.py](../src/reporepublic/sync_artifacts.py)
- tracker-specific handlers can register action-level effects and bundle resolvers without changing the CLI contract

Contract rules:

- `<tracker>` uses a normalized filesystem-safe name such as `local-markdown`
- `issue-<id>` groups staged actions by issue
- filenames are ordered by UTC timestamp so lexicographic sort is chronological
- JSON files are machine-oriented metadata payloads
- Markdown files are human-oriented proposals with YAML frontmatter plus body text

Normalized schema fields:

- `artifact_role`: provider-neutral role such as `comment-proposal`, `branch-proposal`, `pr-proposal`
- `issue_key`: normalized issue reference such as `issue:1`
- `bundle_key`: stable grouping key for related handoff artifacts
- `refs`: normalized branch/base references such as `head` and `base`
- `links`: provider-neutral artifact links such as `self` and `metadata_artifact`

## CLI

List staged artifacts:

```bash
uv run republic sync ls
uv run republic sync ls --issue 1
uv run republic sync ls --tracker local-file --action comment
uv run republic sync ls --tracker local-markdown --action pr-body
uv run republic sync ls --format json
```

Inspect one artifact:

```bash
uv run republic sync show local-markdown/issue-1/20260308T010101000001Z-comment.md
uv run republic sync show 20260308T010101000001Z-comment.md
uv run republic sync show /absolute/path/to/file --raw
```

Apply one pending artifact:

```bash
uv run republic sync apply local-markdown/issue-1/20260308T010101000001Z-comment.md
uv run republic sync apply --issue 1 --tracker local-file --action comment --latest
uv run republic sync apply --issue 1 --tracker local-markdown --action comment --latest
uv run republic sync apply --issue 1 --tracker local-markdown --action pr-body --latest --bundle
uv run republic sync ls --scope applied --issue 1
```

## Current semantics

For `local_markdown` and `local_file`, staged artifacts map to publish proposals such as:

- `comment.md`: issue comment proposal
- `branch.json`: branch creation proposal
- `pr.json`: PR metadata proposal
- `pr-body.md`: PR body proposal
- `labels.json`: label suggestion proposal

The CLI inventory action uses the filename action segment. Tracker-specific metadata can expose a different underlying operation name in YAML or JSON.
The parsed artifact also exposes a normalized metadata block so downstream tooling does not need to understand tracker-specific field names like `branch_name` or `metadata_path`.

## Current apply behavior

For `local_markdown`:

- `comment` artifacts append a `reporepublic` comment entry to the source Markdown issue frontmatter
- `labels` artifacts merge staged labels into the source Markdown issue frontmatter
- `branch`, `pr`, and `pr-body` artifacts are archived into `.ai-republic/sync-applied/` as handled handoff bundles
- `republic sync apply --bundle` resolves the related `branch`, `pr`, and `pr-body` handoff set and archives them together

For `local_file`:

- `comment` artifacts append a `reporepublic` comment entry to the source `issues.json`
- `labels` artifacts merge staged labels into the source `issues.json`
- `branch`, `pr`, and `pr-body` artifacts are archived into `.ai-republic/sync-applied/` as handled handoff bundles
- `republic sync apply --bundle` resolves the related `branch`, `pr`, and `pr-body` handoff set and archives them together

Every apply operation writes or updates:

- `.ai-republic/sync-applied/<tracker>/issue-<id>/manifest.json`

Manifest entries now include richer handoff linkage:

- `entry_key`: stable manifest entry id derived from the source artifact path
- `archived_relative_path`: provider-neutral archive path under `.ai-republic/sync-applied/`
- `handoff.group_key`: bundle or singleton grouping key
- `handoff.group_size` and `handoff.group_index`: ordering inside one handoff group
- `handoff.related_entry_keys` and `handoff.related_source_paths`: links to sibling artifacts in the same handoff set

The source artifact is moved out of `.ai-republic/sync/` unless `--keep-source` is used.

## Dashboard and exports

`republic dashboard` also reads applied manifests and renders a `Sync handoffs` section in every export format.

- HTML: clickable links to `manifest.json`, archived artifacts, and normalized link targets
- JSON: `sync_handoffs[]` entries with `normalized`, `normalized_links`, `handoff`, and archive paths
- Markdown: a handoff summary that can be shared in operator notes or incidents

Useful commands:

```bash
uv run republic dashboard
uv run republic dashboard --format all
uv run republic clean --sync-applied --dry-run
```

When the original staged file has already moved out of `.ai-republic/sync/`, the dashboard resolves normalized links such as `self` and `metadata_artifact` against the applied archive.

`republic clean --sync-applied` is manifest-aware:

- retention is computed per `handoff.group_key`, not per single manifest entry
- older groups beyond `cleanup.sync_applied_keep_groups_per_issue` are pruned together
- orphan archived files and dangling manifest entries are removed conservatively
