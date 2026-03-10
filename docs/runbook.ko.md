# 운영 Runbook

이 문서는 RepoAgents 유지보수자를 위한 day-2 운영 가이드입니다.

## 범위

다음 상황에서 이 문서를 사용합니다.

- 정기 저장소 운영을 시작하거나 중단할 때
- 실패했거나 멈춘 run을 점검할 때
- 특정 issue를 안전하게 다시 실행할 때
- webhook 기반 실행을 검증할 때
- runtime artifact, 로그, dashboard 출력을 검토할 때

## 기본 운영 루프

일반적인 운영 흐름:

1. `uv run repoagents doctor`로 환경 상태를 점검한다
2. `uv run repoagents status`로 최신 상태를 확인한다
3. `uv run repoagents dashboard`로 로컬 대시보드를 갱신한다
4. `uv run repoagents run`으로 polling loop를 실행한다
5. 표적 개입이 필요하면 `uv run repoagents trigger <issue-id>` 또는 `uv run repoagents webhook ...`를 사용한다

## 명령 참고

```bash
uv run repoagents doctor
uv run repoagents doctor --format all
uv run repoagents run
uv run repoagents run --once
uv run repoagents run --dry-run
uv run repoagents trigger 123
uv run repoagents trigger 123 --dry-run
uv run repoagents webhook --event issues --payload webhook.json --dry-run
uv run repoagents status
uv run repoagents status --issue 123
uv run repoagents status --format all
uv run repoagents ops snapshot --archive
uv run repoagents ops status
uv run repoagents ops status --format all
uv run repoagents github smoke --require-write-ready
uv run repoagents ops snapshot --include-cleanup-preview --include-cleanup-result --include-sync-check --include-sync-repair-preview --archive
uv run repoagents ops snapshot --archive --history-limit 10 --prune-history

명령은 아래 latest/history index도 함께 갱신합니다.

- `.ai-repoagents/reports/ops/latest.json`
- `.ai-repoagents/reports/ops/latest.md`
- `.ai-repoagents/reports/ops/history.json`
- `.ai-repoagents/reports/ops/history.md`
- `.ai-repoagents/reports/ops-status.json`
- `.ai-repoagents/reports/ops-status.md`
- `.ai-repoagents/reports/ops-brief.json`
- `.ai-repoagents/reports/ops-brief.md`

`--prune-history`는 `.ai-repoagents/reports/ops/` 아래에서 RepoAgents가 관리하는 bundle/archive만 정리합니다. 외부 custom output directory는 index에는 남지만 ops history prune 대상으로 삭제되지는 않습니다.
uv run repoagents sync ls
uv run repoagents sync show local-markdown/issue-1/<timestamp>-comment.md
uv run repoagents sync health --issue 1 --format all
uv run repoagents sync check --issue 1
uv run repoagents sync repair --issue 1 --dry-run
uv run repoagents sync audit --format all
uv run repoagents sync apply --issue 1 --tracker local-file --action comment --latest
uv run repoagents sync apply --issue 1 --tracker local-markdown --action comment --latest
uv run repoagents clean --sync-applied --dry-run
uv run repoagents clean --sync-applied --dry-run --report --report-format all
uv run repoagents retry 123
uv run repoagents clean --dry-run
uv run repoagents clean
uv run repoagents dashboard
uv run repoagents dashboard --format all
```

## 런타임 경로

- config: `.ai-repoagents/repoagents.yaml`
- state: `.ai-repoagents/state/runs.json`
- artifacts: `.ai-repoagents/artifacts/issue-<id>/<run-id>/`
- workspaces: `.ai-repoagents/workspaces/issue-<id>/<run-id>/repo/`
- dashboard: `.ai-repoagents/dashboard/index.html`
- dashboard JSON snapshot: `.ai-repoagents/dashboard/index.json`
- doctor snapshots: `.ai-repoagents/reports/doctor.json`, `.ai-repoagents/reports/doctor.md`
- status snapshots: `.ai-repoagents/reports/status.json`, `.ai-repoagents/reports/status.md`
- ops status snapshots: `.ai-repoagents/reports/ops-status.json`, `.ai-repoagents/reports/ops-status.md`
- dashboard Markdown snapshot: `.ai-repoagents/dashboard/index.md`
- sync health reports: `.ai-repoagents/reports/sync-health.json`, `.ai-repoagents/reports/sync-health.md`
- sync audit reports: `.ai-repoagents/reports/sync-audit.json`, `.ai-repoagents/reports/sync-audit.md`
- cleanup reports: `.ai-repoagents/reports/cleanup-preview.json`, `.ai-repoagents/reports/cleanup-result.json`
- 로그 활성화 시: `.ai-repoagents/logs/repoagents.jsonl`
- sync staging: `.ai-repoagents/sync/<tracker>/issue-<id>/`
- sync applied archive: `.ai-repoagents/sync-applied/<tracker>/issue-<id>/`

## Dashboard의 sync handoff와 retention

이제 dashboard는 `.ai-repoagents/sync-applied/**/manifest.json`을 읽어 `Sync handoffs`와 `Sync retention`을 함께 보여주고, `.ai-repoagents/reports/ops/latest.*`, `history.*`를 읽는 `Ops snapshots` 섹션과 `.ai-repoagents/reports/` 아래 sync audit, sync health, GitHub smoke, ops status, ops brief, cleanup export를 여는 `Reports` 링크도 제공합니다.

최신 bundle manifest component summary, 현재 handoff brief headline/severity, landing path, recent history preview까지 포함한 ops index posture를 CLI/export 한 화면에서 보고 싶을 때는 `repoagents ops status`를 사용하면 됩니다.
`ops-status.json`이나 `ops-brief.json`이 있으면 dashboard `Reports` 섹션에도 같은 카드가 생기고, 최신 bundle이 참조한 관련 report export와 교차 링크가 같이 표시됩니다. 이제 `repoagents ops snapshot`은 `ops-status.json|md`, `ops-brief.json|md`, live GitHub REST tracker일 때는 `github-smoke.json|md`, bundle landing 파일 `index.html`, `README.md`를 handoff bundle 내부에도 쓰고, repo root의 `ops-status.json|md`, `ops-brief.json|md`, `sync-health.json|md`, live `github-smoke.json|md`도 함께 갱신해서 incident review와 dashboard/report surface가 같은 최신 sync posture, landing summary, GitHub publish readiness를 따라가게 합니다.

다음 상황에서 이 섹션을 사용합니다.

- 어떤 staged publish proposal이 이미 처리됐는지 확인할 때
- archive된 `branch` / `pr` / `pr-body` bundle을 한 화면에서 열어볼 때
- 원본 staged 파일이 이동된 뒤에도 `metadata_artifact` 같은 normalized link를 따라갈 때
- 어떤 applied issue archive가 `stable`, `prunable`, `repair-needed`인지 확인할 때
- `clean` 전에 prunable group 수, prunable bytes, oldest prunable age로 정리 영향 범위를 볼 때

모든 export를 다시 만들려면:

```bash
uv run repoagents dashboard --format all
```

## 정상 점검 항목

live run 전에 확인할 것:

- `codex --version`과 `codex login`
- tracker가 live GitHub REST mode면 `GITHUB_TOKEN`
- `uv run repoagents doctor`
- unattended live write를 켜기 전 `uv run repoagents github smoke --require-write-ready`
- 이 smoke gate는 draft PR publish를 위해 default branch protection, PR review requirement, required status check, readable GitHub repo permission까지 함께 기대함
- `REPOREPUBLIC_GITHUB_WRITE_E2E=1`, `REPOREPUBLIC_GITHUB_PR_E2E=1` 테스트는 반드시 전용 sandbox repo/issue에서 실행하고, comment test는 comment 삭제, draft PR test는 PR close와 branch delete까지 cleanup 단계에서 수행
- `workspace.strategy: worktree`를 쓴다면 대상 저장소가 유효한 Git work tree인지
- 로컬 수정이 있는 저장소라면 `workspace.dirty_policy`

## 장애 대응

### run이 `retry_pending` 상태다

1. `uv run repoagents status --issue <id>`로 최신 run을 본다
2. 실패 run의 role artifact를 연다
3. 필요하면 근본 원인을 먼저 해결한다
4. `uv run repoagents retry <id>`로 즉시 재시도 창을 연다
5. `uv run repoagents dashboard`로 대시보드를 다시 생성한다

### run이 `failed` 상태다

먼저 다음을 확인합니다.

- Codex CLI 설치 및 로그인 상태
- GitHub auth, rate limit, network 상태
- reviewer artifact의 policy finding
- dirty working tree 또는 worktree 설정 문제

그 다음 선택지는 두 가지입니다.

- `uv run repoagents trigger <id>`로 특정 issue를 직접 다시 실행
- 또는 `uv run repoagents retry <id>`로 retry 큐에 다시 넣기

### polling loop가 멈춘 것처럼 보인다

다음 명령으로 먼저 확인합니다.

```bash
uv run repoagents status
uv run repoagents run --once
uv run repoagents dashboard
```

`run --once`가 아무 것도 잡지 못하면:

- tracker 입력 소스를 확인한다
- issue 상태와 label을 확인한다
- 해당 fingerprint가 이미 완료 처리됐는지 확인한다
- 필요할 때만 `trigger`로 일회성 재실행을 건다

### webhook payload가 run을 시작하지 못했다

1. payload를 파일로 저장한다
2. 아래 명령으로 dry-run 검증한다

```bash
uv run repoagents webhook --event issues --payload webhook.json --dry-run
```

3. payload가 열려 있는 issue 번호로 매핑되는지 확인한다
4. 이미 완료된 issue라면 사람 검토 후에만 `trigger --force`를 사용한다

## 안전한 수동 개입 순서

가장 덜 파괴적인 선택부터 사용합니다.

1. `status --issue <id>`로 점검
2. `dashboard`로 대시보드 재생성
3. `retry <id>`로 run 재개
4. `trigger <id> --dry-run`으로 단일 issue 미리보기
5. `trigger <id>`로 단일 issue 실행
6. 정리 전에는 항상 `clean --dry-run`

CLI 정리 경로로 복구되지 않는 경우가 아니면 state/workspace 파일을 직접 삭제하지 않습니다.

## 오프라인 publish handoff

tracker가 publish proposal을 바로 적용하지 않고 로컬에 stage하는 경우:

1. `uv run repoagents sync ls`로 inventory를 확인한다
2. `uv run repoagents sync show ...`로 artifact 하나를 연다
3. 지원되는 tracker helper가 있으면 `uv run repoagents sync apply ...`로 먼저 반영한다. 예: `local-file`, `local-markdown`의 comment/label proposal
4. 남은 handoff proposal만 사람이 수동으로 반영한다
5. `.ai-repoagents/sync-applied/` 아래 archive와 dashboard의 `Sync handoffs` / `Sync retention` 섹션을 함께 확인한다
6. 오래된 applied handoff group을 정리하기 전에는 `uv run repoagents clean --sync-applied --dry-run`으로 먼저 확인한다
   review가 필요하면 `--report --report-format all`로 machine-readable cleanup preview도 남긴다.
7. repair, audit, cleanup 중 무엇을 할지 고르기 전에 `uv run repoagents sync health --issue <id> --format all`로 한 번에 묶인 snapshot을 본다
8. manifest drift가 의심되면 `sync repair` 전에 `uv run repoagents sync check --issue <id>`를 먼저 실행한다
9. 더 좁은 machine-readable audit snapshot이 필요하면 `uv run repoagents sync audit --issue <id> --format all`을 export한다

## 사람 승인 경계

RepoAgents의 기본값은 계속 보수적입니다.

- reviewer approve가 나와도 merge는 자동으로 수행하지 않음
- 위험한 diff는 여전히 사람 판단이 필요함
- docs/tests 변경은 정책에 따라 draft PR까지 갈 수 있지만 merge는 수동
- secrets, CI/CD 변경, auth 민감 경로, 대규모 삭제는 incident로 취급하고 검토

## 권장 운영 주기

매일:

- `doctor`
- `status`
- `dashboard`

incident마다:

- 실패 run을 열어 확인
- artifact와 로그를 수집
- `retry`, `trigger`, 또는 보류 중 무엇을 할지 결정

매주:

- `clean --dry-run` 후 `clean`으로 stale local data 정리
- `repoagents init --upgrade`로 template drift 점검

## 관련 예제

- live GitHub ops 청사진: [../examples/live-github-ops/README.md](../examples/live-github-ops/README.md)
- live GitHub 운영 walkthrough: [./live-github-ops.ko.md](./live-github-ops.ko.md)
- sandbox publish rollout 예제: [../examples/live-github-sandbox-rollout/README.md](../examples/live-github-sandbox-rollout/README.md)
- sandbox publish rollout walkthrough: [./live-github-sandbox-rollout.ko.md](./live-github-sandbox-rollout.ko.md)
- 로컬 webhook receiver: [../examples/webhook-receiver/README.md](../examples/webhook-receiver/README.md)
- 서명 검증이 있는 로컬 webhook receiver: [../examples/webhook-signature-receiver/README.md](../examples/webhook-signature-receiver/README.md)
