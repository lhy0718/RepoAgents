# Security Policy

## Supported versions

RepoRepublic is currently maintained as a rolling `0.1.x` line.

| Version | Supported |
| --- | --- |
| `0.1.x` | Yes |
| `< 0.1.0` preview snapshots | No |

## Reporting a vulnerability

Please do not open public GitHub issues for suspected security vulnerabilities.

Instead:

1. Email the maintainers or use the private reporting channel configured for the repository.
2. Include a clear description of the impact.
3. Include reproduction steps, affected paths, and any required environment details.
4. State whether the issue affects:
   - live GitHub publish paths
   - Codex prompt/policy handling
   - local workspace isolation
   - sync artifact or report export flows

## Response expectations

- Initial acknowledgement target: within 5 business days
- Triage target: within 10 business days
- Fix timeline: depends on severity and exploitability

If the report is accepted, the maintainers will coordinate a fix, tests, documentation updates, and a changelog entry before public disclosure.

## Scope notes

The highest priority issues are:

- unintended live GitHub writes
- workspace escape or repository boundary violations
- secret leakage in logs, reports, or artifacts
- policy bypasses that weaken default human approval behavior
- code paths that allow unsafe publish behavior despite explicit safety settings
