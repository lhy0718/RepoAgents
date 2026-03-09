# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog and the project uses semantic-style version tags for public releases.

## [Unreleased]

### Added

- publish-enabled sandbox rollout example with staged `github smoke` gates and handoff bundle rehearsal
- release preview / announcement CLI surfaces plus local public-preview tag rehearsal demo
- release preflight checklist surface and one-command pre-publish gate

## [0.1.0] - 2026-03-09

### Added

- initial public-preview release of RepoRepublic
- Typer CLI with `init`, `doctor`, `run`, `status`, `trigger`, `webhook`, `dashboard`, `ops`, `sync`, and `github smoke`
- Codex CLI default backend plus deterministic mock backend
- GitHub, `local_file`, and `local_markdown` tracker adapters
- `copy` and `worktree` workspace strategies
- role pipeline with `triage`, `planner`, `engineer`, `reviewer`, and optional `qa`
- sync staging, apply, audit, repair, cleanup, and health surfaces
- dashboard, ops snapshot, ops status, ops brief, and incident handoff bundle flows
- English and Korean documentation, quickstarts, runbooks, and runnable example scripts
