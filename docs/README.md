# Documentation Index

RepoRepublic keeps multilingual documents side-by-side with a simple naming rule:

- English source files use `name.md`
- Korean translations use `name.ko.md`
- New documents should follow the same pattern in the same directory

## Root guides

- English overview: [README.md](../README.md)
- Korean overview: [README.ko.md](../README.ko.md)
- English quickstart: [QUICKSTART.md](../QUICKSTART.md)
- Korean quickstart: [QUICKSTART.ko.md](../QUICKSTART.ko.md)

## Architecture

- English: [architecture.md](./architecture.md)
- Korean: [architecture.ko.md](./architecture.ko.md)

## Extensions

- English: [extensions.md](./extensions.md)
- Korean: [extensions.ko.md](./extensions.ko.md)
- Sync artifacts: [sync.md](./sync.md), [sync.ko.md](./sync.ko.md)
- Role pack examples: [role-packs.md](./role-packs.md), [role-packs.ko.md](./role-packs.ko.md)

## Operations

- English: [runbook.md](./runbook.md)
- Korean: [runbook.ko.md](./runbook.ko.md)
- Live GitHub walkthrough: [live-github-ops.md](./live-github-ops.md), [live-github-ops.ko.md](./live-github-ops.ko.md)
- Sandbox publish rollout: [live-github-sandbox-rollout.md](./live-github-sandbox-rollout.md), [live-github-sandbox-rollout.ko.md](./live-github-sandbox-rollout.ko.md)
- Release process: [release.md](./release.md), [release.ko.md](./release.ko.md)

## Backlog

- Active queue: [backlog/active-queue.md](./backlog/active-queue.md)
- Completed archive: [backlog/issue-queue.md](./backlog/issue-queue.md)

## Examples

- Python library demo: [examples/python-lib/README.md](../examples/python-lib/README.md)
- Web app demo: [examples/web-app/README.md](../examples/web-app/README.md)
- Local file tracker demo: [examples/local-file-inbox/README.md](../examples/local-file-inbox/README.md)
- Local file sync demo: [examples/local-file-sync/README.md](../examples/local-file-sync/README.md)
- Local markdown tracker demo: [examples/local-markdown-inbox/README.md](../examples/local-markdown-inbox/README.md)
- Local markdown sync demo: [examples/local-markdown-sync/README.md](../examples/local-markdown-sync/README.md)
- Docs maintainer pack demo: [examples/docs-maintainer-pack/README.md](../examples/docs-maintainer-pack/README.md)
- Webhook receiver demo: [examples/webhook-receiver/README.md](../examples/webhook-receiver/README.md)
- Signed webhook receiver demo: [examples/webhook-signature-receiver/README.md](../examples/webhook-signature-receiver/README.md)
- Live GitHub ops blueprint: [examples/live-github-ops/README.md](../examples/live-github-ops/README.md)
- Sandbox publish rollout blueprint: [examples/live-github-sandbox-rollout/README.md](../examples/live-github-sandbox-rollout/README.md)
- Release rehearsal: [examples/release-rehearsal/README.md](../examples/release-rehearsal/README.md)
- Release publish dry-run: [examples/release-publish-dry-run/README.md](../examples/release-publish-dry-run/README.md)

## Rule for new docs

When adding a new top-level guide, use this structure:

- English file first, for example `docs/operations.md`
- Korean counterpart beside it, for example `docs/operations.ko.md`
- Add both links to this index and to the root README language section if the guide is a primary entry point
