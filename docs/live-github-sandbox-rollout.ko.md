# Live GitHub Sandbox Publish Rollout

이 문서는 production 저장소에 같은 설정을 적용하기 전에, sandbox GitHub 저장소에서 publish enablement를 단계적으로 rehearsal하는 방법을 설명합니다.

## 언제 이 가이드를 쓰면 좋은가

다음이 목표일 때 사용합니다.

- `tracker.kind: github`, `tracker.mode: rest`를 유지하고 싶을 때
- `allow_write_comments`를 먼저 검증하고, 그 다음 `allow_open_pr`를 켜고 싶을 때
- draft PR publish는 반드시 `github smoke --require-write-ready`로 gate하고 싶을 때
- sandbox gate가 green이 된 뒤에만 최종 handoff bundle을 만들고 싶을 때
- green 상태를 실제 issue execution artifact까지 연결해서 확인하고 싶을 때

## 참고 파일

- [../examples/live-github-sandbox-rollout/README.md](../examples/live-github-sandbox-rollout/README.md)
- [../examples/live-github-sandbox-rollout/ops/preflight.md](../examples/live-github-sandbox-rollout/ops/preflight.md)
- [../examples/live-github-sandbox-rollout/ops/rollout-order.md](../examples/live-github-sandbox-rollout/ops/rollout-order.md)
- [../examples/live-github-sandbox-rollout/ops/execution-order.md](../examples/live-github-sandbox-rollout/ops/execution-order.md)
- [../examples/live-github-sandbox-rollout/ops/set-sandbox-phase.sh](../examples/live-github-sandbox-rollout/ops/set-sandbox-phase.sh)
- [../examples/live-github-sandbox-rollout/ops/rehearse-rollout.sh](../examples/live-github-sandbox-rollout/ops/rehearse-rollout.sh)
- [../examples/live-github-sandbox-rollout/ops/rehearse-execution.sh](../examples/live-github-sandbox-rollout/ops/rehearse-execution.sh)
- [../scripts/demo_live_publish_sandbox.sh](../scripts/demo_live_publish_sandbox.sh)

## phase 모델

1. `baseline`
   live write를 모두 끈 상태입니다. repo, token, origin, branch policy surface가 읽히는지 먼저 확인합니다.
2. `comments-ready`
   comment write만 켜고, draft PR write는 계속 끕니다.
3. `pr-gated`
   draft PR write를 요청하지만, `github smoke --require-write-ready`는 아직 실패해야 합니다.
4. `pr-ready`
   draft PR write를 요청했고 readiness gate도 통과합니다. 이 시점에서만 handoff bundle을 만들어 review합니다.

## 오프라인 rehearsal

번들된 sandbox demo를 실행합니다.

```bash
bash scripts/demo_live_publish_sandbox.sh
```

이 스크립트는 임시 저장소를 만들고, 가짜 `GITHUB_TOKEN`을 설정하고, `tracker.smoke_fixture_path`를 phase fixture로 바꿔 가며 per-phase `doctor`, `github smoke` export를 남긴 뒤, `.ai-repoagents/reports/ops/sandbox-pr-ready/` 아래에 readiness bundle을 만들고, 그 다음 `github fixture + 오프라인 fake Codex shim`으로 잠깐 전환해 issue 하나를 실행한 뒤 `.ai-repoagents/reports/ops/sandbox-issue-201/` 아래에 execution bundle도 생성합니다.

이 rehearsal helper는 phase 전환마다 로컬 commit을 남깁니다. 그래야 `workspace.dirty_policy: block`을 유지한 채 `doctor`를 반복 실행할 수 있습니다.

phase별 report 위치:

- `.ai-repoagents/reports/sandbox-rollout/baseline/`
- `.ai-repoagents/reports/sandbox-rollout/comments-ready/`
- `.ai-repoagents/reports/sandbox-rollout/pr-gated/`
- `.ai-repoagents/reports/sandbox-rollout/pr-ready/`

중요한 gate 파일:

- `.ai-repoagents/reports/sandbox-rollout/pr-gated/require-write-ready.exit-code`
- `.ai-repoagents/reports/sandbox-rollout/pr-ready/require-write-ready.exit-code`

기대값:

- `pr-gated`: `1`
- `pr-ready`: `0`

## deterministic execution rehearsal

publish gate가 green이 된 뒤에는 예제가 issue 하나를 오프라인 실행 모드로 돌립니다.

- `tracker.mode=fixture`
- `tracker.fixtures_path=issues.json`
- `llm.mode=codex`

이 경로는 아래를 남깁니다.

- `.ai-repoagents/reports/sandbox-execution/trigger-dry-run.txt`
- `.ai-repoagents/reports/sandbox-execution/trigger.txt`
- `.ai-repoagents/reports/sandbox-execution/status.json|md`
- `.ai-repoagents/artifacts/issue-201/<run-id>/...`
- `.ai-repoagents/reports/ops/sandbox-issue-201/`

실행 후에는 config를 다시 live `tracker.mode=rest`, `llm.mode=codex` 상태로 복구하므로, 데모 종료 시점의 저장소는 publish-enabled sandbox posture를 유지합니다.

## 실제 sandbox 저장소에서 같은 흐름을 쓰는 방법

1. sandbox 저장소를 로컬에 clone합니다.
2. 그 안에서 `repoagents init`을 실행합니다.
3. 설정을 `tracker.kind: github`, `tracker.mode: rest`, `workspace.strategy: worktree`, `logging.file_enabled: true`로 맞춥니다.
4. 시작값은 다음처럼 둡니다.

```yaml
safety:
  allow_write_comments: false
  allow_open_pr: false
```

5. `uv run repoagents doctor`를 실행합니다.
6. `uv run repoagents github smoke --format all`을 실행합니다.
7. comment write만 켜고 같은 smoke를 반복합니다.
8. sandbox에서 draft PR write를 켠 뒤 아래 명령을 반드시 통과시킵니다.

```bash
uv run repoagents github smoke --require-write-ready
```

이 명령이 계속 non-zero로 끝나면, sandbox branch policy를 고치기 전까지는 `allow_open_pr=true`를 유지하지 말아야 합니다.

## readiness를 실제 issue execution에 연결하기

실제 sandbox 저장소에서 comment나 draft PR publish를 켜기 전에, artifact 흐름이 맞는지 issue 하나로 먼저 검증하는 편이 안전합니다.

1. 같은 저장소 checkout에서 `pr-ready` green 상태를 유지합니다.
2. fixture issue source와 deterministic backend로 잠깐 전환합니다.
3. `trigger`로 issue 하나를 실행합니다.
4. artifact, status, execution handoff bundle을 확인합니다.
5. 저장소를 live sandbox config로 다시 복구합니다.

번들된 helper는 이 흐름을 그대로 수행합니다.

```bash
bash ops/rehearse-execution.sh
```

열어볼 순서는 [../examples/live-github-sandbox-rollout/ops/execution-order.md](../examples/live-github-sandbox-rollout/ops/execution-order.md)에 고정해 두었습니다.

## 최종 handoff bundle

`pr-ready`가 clean이 된 뒤에만 아래 bundle을 만듭니다.

```bash
uv run repoagents ops snapshot \
  --output-dir .ai-repoagents/reports/ops/sandbox-pr-ready \
  --include-sync-check \
  --include-sync-repair-preview \
  --archive
```

그 다음 아래를 갱신합니다.

```bash
uv run repoagents ops status --format all
uv run repoagents dashboard --refresh-seconds 30 --format all
```

bundle open 순서:

1. `index.html`
2. `ops-brief.md`
3. `github-smoke.md`
4. `ops-status.md`
5. `dashboard.html`

정확한 rehearsal 순서는 [../examples/live-github-sandbox-rollout/ops/rollout-order.md](../examples/live-github-sandbox-rollout/ops/rollout-order.md)를 따르면 됩니다.

## 안전 메모

- `merge_policy.mode: human_approval`을 유지합니다.
- sandbox publish는 production automation이 아니라 rehearsal로 취급합니다.
- 실제 sandbox 저장소에 같은 명령을 적용하기 전에는 `tracker.smoke_fixture_path`를 제거해야 합니다.
- production에서 unattended write를 켜기 전에는 sandbox 경로가 먼저 통과했고, handoff bundle review도 끝났는지 확인해야 합니다.
