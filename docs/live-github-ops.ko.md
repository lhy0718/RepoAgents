# Live GitHub 운영 walkthrough

이 문서는 `examples/live-github-ops` 청사진을 실제 GitHub 저장소 운영 절차로 풀어쓴 단계별 가이드입니다.

## 언제 이 문서를 쓰나

다음 상황에서 사용합니다.

- fixture 또는 mock 데모에서 live GitHub issue polling으로 넘어갈 때
- Codex CLI를 기본 worker runtime으로 유지할 때
- 보수적인 human approval 정책으로 RepoRepublic를 연속 운영할 때
- 큰 플랫폼을 만들기 전, 로컬 머신이나 VM, 간단한 프로세스 매니저 위에서 먼저 운영할 때

## 사전 준비

live 저장소를 건드리기 전에 아래를 확인합니다.

- RepoRepublic checkout에서 `uv sync --dev`가 끝나 있음
- `codex --version`, `codex login`이 정상 동작함
- `GITHUB_TOKEN`이 export되어 있고, issue read 권한과 필요한 경우에만 comment/PR write 권한이 있음
- 대상 저장소가 로컬에 clone되어 있고 기준 상태가 깨끗함
- 현재 `merge_policy.mode`, `safety.*` 설정을 이해하고 있음

보수적인 기본 경로는 다음을 유지하는 것입니다.

- `llm.mode: codex`
- `merge_policy.mode: human_approval`
- `safety.allow_write_comments: false` 또는 엄격히 통제된 상태
- dry-run과 단일 issue trigger가 안정적일 때까지 `safety.allow_open_pr: false`

## 참고 파일

live 청사진 예제는 아래에 있습니다.

- [../examples/live-github-ops/README.md](../examples/live-github-ops/README.md)
- [../examples/live-github-ops/ops/preflight.md](../examples/live-github-ops/ops/preflight.md)
- [../examples/live-github-ops/ops/republic.env.example](../examples/live-github-ops/ops/republic.env.example)
- [../examples/live-github-ops/ops/run-loop.sh](../examples/live-github-ops/ops/run-loop.sh)
- [../examples/live-github-ops/ops/render-dashboard.sh](../examples/live-github-ops/ops/render-dashboard.sh)

## 1단계. 대상 저장소를 clone한다

RepoRepublic가 유지보수할 실제 저장소에서 시작합니다.

```bash
git clone git@github.com:OWNER/REPO.git
cd REPO
git status --short
```

working tree가 이미 dirty 상태면 먼저 정리하거나, 최소한 `workspace.dirty_policy`를 의도적으로 설정해야 합니다. live 운영에서는 `block`이 가장 안전합니다.

## 2단계. 저장소 안에 RepoRepublic를 초기화한다

대상 저장소 내부에서 초기화를 실행합니다.

```bash
uv run --project /path/to/RepoRepublic republic init \
  --preset python-library \
  --tracker-repo OWNER/REPO
```

저장소 성격이 더 가깝다면 `web-app`, `docs-only`, `research-project` preset을 사용해도 됩니다.

이 단계에서 다음이 생성됩니다.

- `.ai-republic/reporepublic.yaml`
- `AGENTS.md`
- `WORKFLOW.md`
- `.ai-republic/roles/`
- `.ai-republic/prompts/`
- `.ai-republic/policies/`

## 3단계. 설정을 live GitHub 모드로 맞춘다

`.ai-republic/reporepublic.yaml`을 열고 아래 값들을 확인합니다.

권장 기본값:

```yaml
tracker:
  kind: github
  mode: rest
  repo: OWNER/REPO
  poll_interval_seconds: 300

workspace:
  strategy: worktree
  dirty_policy: block

logging:
  json: true
  file_enabled: true

llm:
  mode: codex

merge_policy:
  mode: human_approval

safety:
  allow_write_comments: false
  allow_open_pr: false
```

이 설정을 권장하는 이유:

- `tracker.mode: rest`는 live GitHub adapter를 사용함
- `workspace.strategy: worktree`는 큰 저장소에서 더 현실적임
- `logging.file_enabled: true`는 `.ai-republic/logs/reporepublic.jsonl`에 운영 흔적을 남김
- `human_approval`은 rollout 초기에 publication과 merge를 보수적으로 유지함

## 4단계. 환경 변수를 준비한다

청사진 env 파일을 시작점으로 사용합니다.

```bash
cp /path/to/RepoRepublic/examples/live-github-ops/ops/republic.env.example ./.ai-republic/republic.env
```

그 다음 shell, direnv, systemd environment, 또는 별도 secrets manager로 실제 값을 주입합니다.

최소 live 환경:

```bash
export GITHUB_TOKEN=...
```

Codex CLI가 이미 로컬에서 로그인돼 있다면 Codex 자격 증명을 저장소 안에 둘 필요는 없습니다.

## 5단계. `doctor`를 먼저 돌린다

단일 issue도 실행하기 전에 환경을 검증합니다.

```bash
uv run --project /path/to/RepoRepublic republic doctor
```

건강한 경로에서 기대하는 결과:

- config가 정상 로드됨
- Codex command가 실행 가능함
- GitHub auth와 network 체크가 통과함
- runtime 디렉터리에 쓸 수 있음
- `worktree` 모드라면 저장소가 유효한 git work tree임
- 예상치 못한 managed template drift가 없음

`doctor`가 깨끗하지 않으면, 경고가 왜 나는지 이해하기 전까지 live 실행으로 넘어가지 않는 편이 안전합니다.

## 6단계. 먼저 단일 issue dry-run을 본다

polling loop를 켜기 전에 표적 dry-run을 실행합니다.

```bash
uv run --project /path/to/RepoRepublic republic trigger 123 --dry-run
```

이때 볼 것:

- issue 선택이 맞는지
- role 순서가 맞는지
- planner의 `likely_files`가 그럴듯한지
- 막힌 side effect가 정책과 일치하는지
- backend가 `mock`이 아니라 `codex`인지

특정 issue 번호를 아직 고르기 어렵다면, 다음 poll cycle을 보기 위해 `republic run --dry-run --once`도 유용합니다.

## 7단계. polling loop 전에 issue 하나만 실행한다

dry-run이 깨끗하면 issue 하나만 실제 실행합니다.

```bash
uv run --project /path/to/RepoRepublic republic trigger 123
uv run --project /path/to/RepoRepublic republic status --issue 123
```

생성된 데이터를 직접 확인합니다.

- `.ai-republic/artifacts/issue-123/<run-id>/` 아래 artifact
- `.ai-republic/workspaces/issue-123/<run-id>/repo/` 또는 worktree 경로
- `.ai-republic/state/runs.json`
- `.ai-republic/logs/reporepublic.jsonl`

reviewer나 policy guardrail이 `request_changes`를 반환해도, rollout 단계에서는 그 자체가 정상적인 안전장치 동작일 수 있습니다.

## 8단계. 장기 실행 loop를 시작한다

단일 issue 동작이 예상대로 보이면 loop를 시작합니다.

```bash
bash /path/to/RepoRepublic/examples/live-github-ops/ops/run-loop.sh
```

이 helper script는 사실상 아래 명령을 감싼 얇은 wrapper입니다.

```bash
uv run republic run
```

실운영에서는 `systemd`, `launchd`, container runtime, 또는 스케줄러가 있는 CI runner 같은 supervisor 아래에서 돌리는 편이 좋습니다.

## 9단계. 대시보드를 렌더링하고 본다

운영 대시보드는 주기적으로 다시 생성합니다.

```bash
bash /path/to/RepoRepublic/examples/live-github-ops/ops/render-dashboard.sh
```

또는 직접:

```bash
uv run republic dashboard --refresh-seconds 30
```

브라우저에서 `.ai-republic/dashboard/index.html`을 열고 다음을 활용합니다.

- 검색으로 특정 issue를 빠르게 찾기
- status filter로 failure/retry만 보기
- 운영 중 페이지를 띄워둘 때 timed refresh 사용하기

## 10단계. 실패를 안전하게 다룬다

가장 덜 파괴적인 복구 경로부터 사용합니다.

실패했거나 retry 대기 중인 issue라면:

```bash
uv run republic status --issue 123
uv run republic retry 123
uv run republic trigger 123 --dry-run
uv run republic trigger 123
```

workspace 정리가 필요해도 먼저 `clean --dry-run`을 봅니다.

```bash
uv run republic clean --dry-run
uv run republic clean
```

문제가 GitHub auth, Codex login, rate limit, dirty worktree에 있다면 그 원인을 먼저 해결한 뒤 issue를 다시 실행합니다.

## 11단계. write path는 천천히 연다

첫날부터 comment나 draft PR을 열 필요는 없습니다.

권장 rollout:

1. `allow_write_comments: false`, `allow_open_pr: false`로 시작
2. 단일 issue run이 여러 번 안정적으로 끝난 뒤 issue comment 허용 검토
3. reviewer와 policy 동작이 안정적일 때만 `allow_open_pr: true` 검토
4. draft PR 생성이 열려 있어도 merge는 계속 사람이 수행

## 선택 사항: webhook 진입점 추가

MVP rollout에서는 polling만으로도 충분하지만, 더 빠른 반응이 필요하면 webhook 경로를 붙일 수 있습니다.

관련 경로:

- [runbook.ko.md](./runbook.ko.md)
- [../examples/webhook-receiver/README.md](../examples/webhook-receiver/README.md)
- [../scripts/webhook_receiver.py](../scripts/webhook_receiver.py)

live receiver에 붙이기 전에는 다음으로 payload를 검증합니다.

```bash
uv run republic webhook --event issues --payload webhook.json --dry-run
```

## rollout 체크리스트

실운영 전환 전에는 아래를 확인합니다.

- `doctor`가 깨끗함
- 최소 1번의 `trigger --dry-run`과 1번의 `trigger`가 성공적으로 끝남
- operator가 artifact와 로그를 읽을 수 있음
- dashboard가 정상 렌더링됨
- `dirty_policy`, publication policy, safety flag가 저장소 리스크에 맞음
- RepoRepublic가 `request_changes`를 낼 때 사람이 어떻게 판단할지 경로가 명확함

## 관련 문서

- [runbook.ko.md](./runbook.ko.md)
- [extensions.ko.md](./extensions.ko.md)
- [../examples/live-github-ops/README.md](../examples/live-github-ops/README.md)
