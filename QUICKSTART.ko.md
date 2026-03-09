# Quickstart

한국어 문서입니다. 영문 원문은 [QUICKSTART.md](./QUICKSTART.md)에서 볼 수 있습니다.

## 1. 의존성 설치

```bash
uv sync --dev
codex --version
```

Codex 로그인이 아직 안 되어 있다면:

```bash
codex login
```

선택적으로 실제 Codex smoke test를 실행할 수 있습니다.

```bash
CODEX_E2E=1 uv run pytest tests/test_codex_backend.py -k live_smoke -rs
GITHUB_E2E=1 REPOREPUBLIC_GITHUB_TEST_REPO=owner/name uv run pytest tests/test_tracker.py -k live_read_only -rs
```

## 2. 대상 저장소 초기화

```bash
cd /path/to/your/repo
uv run republic init
uv run republic init --preset python-library --tracker-repo owner/name
uv run republic init --tracker-kind local_file --tracker-path issues.json
uv run republic doctor
uv run republic ops snapshot --archive
uv run republic ops snapshot --archive --history-limit 5 --prune-history
uv run republic ops status
cat .ai-republic/reports/ops/latest.json
```

`uv run republic init`을 플래그 없이 실행하면 대화형 초기화가 시작됩니다. 초기 설정을 deterministic mock backend로 두고 싶다면 `--backend mock`을 사용하면 됩니다. GitHub 없이 로컬 JSON inbox로만 돌리려면 `--tracker-kind local_file`를 사용하면 됩니다.

생성되는 제어 파일:

- `.ai-republic/reporepublic.yaml`
- `.ai-republic/roles/*`
- `.ai-republic/prompts/*`
- `.ai-republic/policies/*`
- `AGENTS.md`
- `WORKFLOW.md`

나중에 로컬 수정 보존 상태로 managed template drift를 점검하려면:

```bash
uv run republic init --upgrade
uv run republic init --upgrade --force
```

## 3. 로컬 결정적 데모 실행

빠른 경로:

```bash
bash scripts/demo_python_lib.sh
bash scripts/demo_web_app.sh
bash scripts/demo_local_file_tracker.sh
bash scripts/demo_local_file_sync.sh
bash scripts/demo_local_markdown_tracker.sh
bash scripts/demo_local_markdown_sync.sh
bash scripts/demo_qa_role_pack.sh
bash scripts/demo_webhook_receiver.sh
bash scripts/demo_webhook_signature_receiver.sh
bash scripts/demo_live_ops.sh
```

이 스크립트들은 예제 저장소를 임시 작업 디렉터리로 복사해서, 체크인된 예제 파일을 건드리지 않고 데모를 재현합니다.

```bash
cd examples/python-lib
uv run republic init --preset python-library --fixture-issues issues.json --tracker-repo demo/python-lib
python3 - <<'PY'
from pathlib import Path
path = Path(".ai-republic/reporepublic.yaml")
body = path.read_text()
path.write_text(body.replace("mode: codex", "mode: mock"))
PY
uv run republic run --dry-run
uv run republic run --once
uv run republic status
uv run republic dashboard
uv run republic ops snapshot --include-cleanup-preview --include-cleanup-result --include-sync-check --include-sync-repair-preview --archive
uv run republic ops status --format all
cat .ai-republic/reports/ops/history.json
```

`ops snapshot` history retention 기본값은 `cleanup.ops_snapshot_keep_entries`입니다. dropped managed bundle/archive를 `.ai-republic/reports/ops/` 아래에서 함께 정리하고 싶을 때만 `--prune-history`를 사용하면 됩니다.
dashboard를 열지 않고 최신 indexed handoff bundle과 recent history를 한 번에 확인하려면 `ops status`를 사용하면 됩니다.

optional role pack 동작을 보려면 아래 예제를 사용하면 됩니다.

```bash
cd examples/qa-role-pack
bash ../../scripts/demo_qa_role_pack.sh
```

서명 검증이 켜진 로컬 webhook receiver 경로를 보려면 아래 예제를 사용하면 됩니다.

```bash
cd examples/webhook-signature-receiver
bash ../../scripts/demo_webhook_signature_receiver.sh
```

실제 외부 쓰기 없이 GitHub REST 운영 청사진을 보려면 아래 예제를 사용하면 됩니다.

```bash
cd examples/live-github-ops
bash ../../scripts/demo_live_ops.sh
```

무슨 일이 일어나는지:

1. RepoRepublic가 GitHub tracker adapter의 fixture mode로 issue를 읽습니다.
2. dry-run에서는 `triage`와 `planner`를 미리 실행해 결과를 보여줍니다.
3. `--once`에서는 전체 파이프라인을 실행하고 artifact와 상태를 저장합니다.

GitHub를 쓰지 않고 완전히 로컬로만 돌리려면 아래처럼 설정할 수 있습니다.

```yaml
tracker:
  kind: local_file
  path: issues.json
```

이 경로를 바로 재현하는 번들 예제는 다음입니다.

```bash
cd examples/local-file-inbox
uv run republic init --preset python-library --tracker-kind local_file --tracker-path issues.json --backend mock
uv run republic trigger 1
uv run republic dashboard
```

```bash
cd examples/local-file-sync
bash ../../scripts/demo_local_file_sync.sh
```

```bash
cd examples/local-markdown-inbox
uv run republic init --preset python-library --tracker-kind local_markdown --tracker-path issues --backend mock
uv run republic trigger 1
uv run republic dashboard
```

```bash
cd examples/local-markdown-sync
bash ../../scripts/demo_local_markdown_sync.sh
```

이 경로는 tracker는 오프라인으로 유지하면서 publish 제안을 `.ai-republic/sync/local-markdown/issue-1/` 아래에 stage합니다.
`uv run republic sync ls --issue 1`로 staged inventory를 보고, `uv run republic sync show ...`로 proposal 하나를 열 수 있습니다.
`uv run republic sync apply --issue 1 --tracker local-markdown --action comment --latest`를 실행하면 최신 comment proposal이 원본 Markdown issue에 반영되고, 처리된 artifact는 `.ai-republic/sync-applied/`로 이동합니다.
`uv run republic sync apply --issue 1 --tracker local-markdown --action pr-body --latest --bundle`을 실행하면 관련 branch/PR handoff set을 한 번에 archive할 수 있습니다.
같은 JSON inbox 경로에서는 `uv run republic sync apply --issue 1 --tracker local-file --action comment --latest`를 사용하면 됩니다.
`uv run republic sync check --issue 1`로 applied manifest 무결성을 확인하고, `uv run republic sync repair --issue 1 --dry-run`으로 canonicalize/adopt 결과를 미리 볼 수 있습니다.
오래된 applied handoff group을 지우기 전에는 `uv run republic clean --sync-applied --dry-run`으로 manifest-aware retention 결과를 먼저 확인합니다.
`uv run republic dashboard --format all`을 실행하면 `Sync handoffs`와 함께 `Sync retention`도 볼 수 있고, prunable group 수, prunable bytes, oldest prunable age를 한눈에 확인할 수 있습니다.

## 4. 운영 모드로 전환

`.ai-republic/reporepublic.yaml`을 수정합니다.

```yaml
tracker:
  kind: github
  repo: owner/name
  mode: rest
llm:
  mode: codex
codex:
  command: codex
  model: gpt-5.4
```

그 다음 토큰을 설정하고 polling을 시작합니다.

```bash
export GITHUB_TOKEN=...
uv run republic doctor
uv run republic run
```

polling 대신 event-driven으로 실행하려면:

```bash
uv run republic trigger 123 --dry-run
uv run republic webhook --event issues --payload webhook.json --dry-run
```

## 5. 결과 확인

- artifact: `.ai-republic/artifacts/issue-<id>/<run-id>/`
- debug artifact 활성화 시: `<role>.prompt.txt`, `<role>.raw-output.txt`
- workspace: `.ai-republic/workspaces/issue-<id>/<run-id>/repo/`
- run state: `.ai-republic/state/runs.json`
- dashboard: `.ai-republic/dashboard/index.html`
- dashboard JSON snapshot: `.ai-republic/dashboard/index.json`
- dashboard Markdown snapshot: `.ai-republic/dashboard/index.md`
- sync audit reports: `.ai-republic/reports/sync-audit.json`, `.ai-republic/reports/sync-audit.md`
- cleanup reports: `.ai-republic/reports/cleanup-preview.json`, `.ai-republic/reports/cleanup-result.json`
- doctor snapshots: `.ai-republic/reports/doctor.json`, `.ai-republic/reports/doctor.md`
- status snapshots: `.ai-republic/reports/status.json`, `.ai-republic/reports/status.md`
- 선택적 JSONL 로그: `.ai-republic/logs/reporepublic.jsonl`
- 특정 이슈 상태: `uv run republic status --issue 123`
- operator health snapshot export: `uv run republic doctor --format all`, `uv run republic status --format all`
- 특정 이슈 즉시 실행: `uv run republic trigger 123`
- GitHub webhook payload 검증: `uv run republic webhook --event issues --payload webhook.json --dry-run`
- 즉시 재시도 예약: `uv run republic retry 123`
- 오래된 local 정리 미리보기: `uv run republic clean --dry-run`
- applied sync archive 정리 미리보기: `uv run republic clean --sync-applied --dry-run`
- cleanup preview/report export: `uv run republic clean --sync-applied --dry-run --report --report-format all`
- applied manifest 무결성 검사: `uv run republic sync check --issue 123`
- applied manifest repair 미리보기: `uv run republic sync repair --issue 123 --dry-run`
- sync audit bundle export: `uv run republic sync audit --format all`
- 로컬 대시보드 다시 생성: `uv run republic dashboard`
- timed reload가 있는 대시보드 생성: `uv run republic dashboard --refresh-seconds 30`
- HTML, JSON, Markdown을 함께 export: `uv run republic dashboard --format all`

## 프리셋

- `python-library`: Python 패키지 또는 서비스 저장소
- `web-app`: 프런트엔드 또는 풀스택 앱
- `docs-only`: 문서 중심 저장소
- `research-project`: 노트북/실험 중심 코드베이스

## 기본 안전 정책

- 머지는 사람이 직접 수행
- dry-run에서는 모든 외부 쓰기 차단
- PR 열기는 기본적으로 비활성화
- dirty working tree는 기본적으로 경고만 내고, 설정으로 `block` 또는 `allow`로 바꿀 수 있음
- 민감한 diff는 reviewer 노트와 policy guardrail로 에스컬레이션
