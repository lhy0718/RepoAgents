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

Inspect or repair applied manifest integrity:

```bash
uv run republic sync check --issue 1
uv run republic sync repair --issue 1 --dry-run
uv run republic sync repair --issue 1
uv run republic sync audit --format all
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

`republic dashboard` also reads applied manifests and renders `Sync handoffs`, `Sync retention`, and `Reports` in every export format.

- HTML: clickable links to `manifest.json`, archived artifacts, normalized link targets, and per-issue retention posture cards
- JSON: `sync_handoffs[]` plus `sync_retention` with prunable group counts, bytes, integrity state, and per-group age/size data
- Markdown: a handoff summary plus a retention rollup that can be shared in operator notes or incidents
- Reports: direct dashboard links to `.ai-republic/reports/sync-audit.*`, `cleanup-preview.*`, and `cleanup-result.*` when those exports exist

For `Sync audit`, the dashboard report card also surfaces applied manifest integrity detail from the exported report:

- total integrity reports scanned
- issues with findings vs clean issues
- top finding counts such as `missing_manifest` or `duplicate_entry_key`
- a short sample of affected issue ids

When the sync audit export already links cleanup previews or cleanup results, the dashboard report cards cross-reference each other:

- `Sync audit` links to the related cleanup report cards
- `Cleanup preview` and `Cleanup result` show that they are referenced by `Sync audit`

The `Sync audit` card also translates integrity finding codes into operator hints, for example:

- `missing_manifest`: rebuild manifest state with `republic sync repair --dry-run`
- `duplicate_entry_key`: canonicalize duplicate entries with `republic sync repair --dry-run`
- `orphan_archive_file`: review and adopt orphan archives before applying cleanup

Cleanup report cards also expose freshness metadata:

- `fresh`, `aging`, `stale`, or `future` status derived from dashboard render time vs report `generated_at`
- human-readable age such as `3d 2h`
- the same `freshness` and `age` fields in dashboard JSON and Markdown exports

The dashboard `Sync audit` card also surfaces cleanup report mismatch warnings when a linked cleanup export was generated with a different `issue_filter` than the audit snapshot:

- the mismatch count appears in the report metrics
- warning strings are included in the report detail list for HTML, JSON, and Markdown exports

The `Reports` summary metrics now also aggregate cleanup report freshness across the exported cleanup previews and cleanup results:

- the HTML dashboard shows a `Cleanup freshness` metric with the current `fresh`, `aging`, and `stale` counts
- the dashboard snapshot exposes the same aggregate in JSON and Markdown exports

The dashboard also aggregates freshness across the full report set, not just cleanup exports:

- the HTML `Reports` metric row includes `Report freshness` for all exported reports
- dashboard JSON and Markdown snapshots include the same full-report freshness aggregate

The metric row also breaks aging reports out into a dedicated counter:

- the HTML dashboard includes an `Aging reports` card
- dashboard JSON and Markdown snapshots include the same aging report count

Future-dated reports are also broken out into their own counter:

- the HTML dashboard includes a `Future reports` card
- dashboard JSON and Markdown snapshots include the same future report count

Reports whose freshness cannot be computed are surfaced as an operator warning:

- the HTML dashboard conditionally shows an `Unknown freshness reports` card when the count is non-zero
- dashboard JSON and Markdown snapshots include the same unknown report count

Cleanup-specific aging reports are also broken out into their own counter:

- the HTML dashboard includes a `Cleanup aging reports` card whenever cleanup exports are present
- dashboard JSON and Markdown snapshots include the same cleanup aging report count

Cleanup-specific future-dated reports are also broken out into their own counter:

- the HTML dashboard includes a `Cleanup future reports` card whenever cleanup exports are present
- dashboard JSON and Markdown snapshots include the same cleanup future report count

Cleanup reports whose freshness cannot be computed are surfaced as their own warning:

- when the count is non-zero, the HTML dashboard shows a `Cleanup unknown freshness reports` card
- dashboard JSON and Markdown snapshots include the same cleanup unknown report count

The overall `Report freshness` and cleanup-specific `Cleanup freshness` aggregates now also carry a severity level:

- `issues` when freshness metadata is missing or stale reports are present
- `attention` when only aging or future-dated reports are present
- `clean` when freshness is current or there are no exported reports yet

These severity decisions are repo-configurable through `dashboard.report_freshness_policy`:

- `unknown_issues_threshold`
- `stale_issues_threshold`
- `future_attention_threshold`
- `aging_attention_threshold`

The dashboard hero banner also mirrors the effective severity, title, and reason so operators see report-health posture before scanning the detailed `Reports` cards. That dashboard-only severity now also folds in raw export policy drift, so embedded-policy mismatches can raise the hero to `attention` even when freshness counts are otherwise clean.

`republic doctor` now reports the effective `dashboard.report_freshness_policy` thresholds as well, warns when issue escalation is configured so loosely that stale or unknown reports may stay below `issues` longer than expected, flags raw `sync-audit.json` / `cleanup-*.json` exports whose embedded policy summary no longer matches the live config, and emits a combined `Report policy health` summary that rolls both signals into one operator-facing line. The alignment check now also emits the same related-report detail block shape used by `sync audit` / `clean --report`, so policy drift warnings and remediation read the same way across CLI surfaces.

`republic status` now reuses the same report-health snapshot and prints the current report freshness severity, reason, cleanup report posture, active policy summary, and a combined `policy_health` line alongside persisted run state. When raw report exports still carry an older embedded policy summary, `status` also prints a `policy_warning` line followed by the same related-report detail block shape used by the sync/cleanup commands, including the mismatched file summaries and remediation guidance.

`republic sync audit` now also prints linked cleanup policy drift counts in its CLI summary, and `republic clean --report` prints linked sync-audit policy drift counts next to the export paths so operators can spot cross-report drift without opening the raw JSON first. Add `--show-remediation` to either command when you also want the recommended re-export guidance inline. Add `--show-mismatches` when you also want linked issue-filter mismatch warnings printed inline in the same CLI summary. When both flags are enabled, the CLI emits one related-report detail block that groups mismatch warnings, policy-drift warnings, and remediation guidance together.

Dashboard exports now also include explicit `policy.report_freshness_policy` metadata and a rendered summary string, so downstream automation or shared snapshots can see the exact thresholds that produced the current severity.

Each report entry now carries the same policy context directly in its own detail payload and HTML card, so operators do not need to jump back to the global metadata row to understand the thresholds behind a specific report card.

The dashboard also compares each report card's embedded raw `policy.summary` against the live config and surfaces `Policy drift reports` when older exports no longer match the current thresholds. Per-report cards expose both the live and embedded policy summaries plus the same remediation guidance that `doctor` and `status` print, so operators can decide whether to regenerate the raw report without switching surfaces.

Dashboard Markdown snapshots now also mirror the CLI related-report detail block. Report entries keep their compact `details=` summary, but now also add a `related_report_details` block when linked mismatch warnings or related-report policy drifts exist, including the same remediation guidance text when drift is present.

The raw `sync-audit.json` / `cleanup-*.json` exports now also carry that remediation guidance directly:

- each related report `policy_alignment` block includes `remediation`
- each related-report drift summary entry includes `remediation`
- Markdown exports include `policy_remediation` / `remediation` lines so operators can act without opening the JSON

The dashboard `Cross references` panel now also carries related-report policy drift notes. If a linked cleanup export or sync audit export was rendered with an older embedded policy, the related card warns about that mismatch inline instead of hiding it only in the raw report JSON.

The dashboard also breaks out stale cleanup exports into a dedicated summary card:

- the HTML `Reports` metric row includes `Stale cleanup reports`
- dashboard JSON and Markdown snapshots include the same stale cleanup count

Useful commands:

```bash
uv run republic dashboard
uv run republic dashboard --format all
uv run republic clean --sync-applied --dry-run
uv run republic clean --sync-applied --dry-run --report --report-format all
```

When the original staged file has already moved out of `.ai-republic/sync/`, the dashboard resolves normalized links such as `self` and `metadata_artifact` against the applied archive.

The `Sync retention` snapshot uses `cleanup.sync_applied_keep_groups_per_issue` to classify each applied issue archive as:

- `stable`: no integrity findings and no prunable groups under the current keep limit
- `prunable`: integrity is clean, but at least one older handoff group can be removed
- `repair-needed`: manifest integrity findings exist, so retention should wait until `sync repair` or manual inspection

Each retention entry reports:

- total, kept, and prunable handoff groups
- kept and prunable bytes
- newest group age, oldest group age, and oldest prunable group age
- sample grouped actions such as `branch,pr` or `comment`

`republic clean --sync-applied` is manifest-aware:

- retention is computed per `handoff.group_key`, not per single manifest entry
- older groups beyond `cleanup.sync_applied_keep_groups_per_issue` are pruned together
- orphan archived files and dangling manifest entries are removed conservatively

When `--report` is enabled, cleanup also exports `.ai-republic/reports/cleanup-preview.json|md` or `.ai-republic/reports/cleanup-result.json|md`:

- JSON: action list, affected issues, and manifest replacement counts
- Markdown: operator-friendly cleanup summary

`republic sync check` and `republic sync repair` focus on integrity instead of retention:

- `sync check` reports malformed manifests, duplicate `entry_key`, dangling archive references, handoff linkage mismatches, and orphan archive files
- `sync repair` canonicalizes surviving entries, reconstructs missing metadata, rebuilds handoff linkage, and adopts orphan archives into `manifest.json`

`republic sync audit` exports a consolidated report under `.ai-republic/reports/`:

- JSON: pending staged inventory, applied manifest integrity findings, and retention summary in one payload
- Markdown: incident-friendly operator summary for handoff or async review
- Cross-links: matching `cleanup-preview.*` and `cleanup-result.*` exports are summarized and linked from the sync audit snapshot when available
- Mismatch warnings: cleanup exports with a different `issue_filter` are reported separately so they do not look like valid matches
- Policy metadata: both raw sync audit and cleanup reports now include the active `report_freshness_policy` thresholds directly in their JSON and Markdown output
- Cross-linked policy drift: raw sync audit entries now record `policy_alignment` for linked cleanup exports, and raw cleanup reports now cross-link the latest sync audit export with the same `policy_alignment` contract
- exit status: `1` when applied manifest integrity issues exist, `0` otherwise
