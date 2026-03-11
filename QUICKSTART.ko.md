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
REPOREPUBLIC_GITHUB_WRITE_E2E=1 REPOREPUBLIC_GITHUB_WRITE_TEST_REPO=owner/name REPOREPUBLIC_GITHUB_WRITE_TEST_ISSUE=123 uv run pytest tests/test_tracker.py -k live_comment_write -rs
REPOREPUBLIC_GITHUB_PR_E2E=1 REPOREPUBLIC_GITHUB_PR_TEST_REPO=owner/name REPOREPUBLIC_GITHUB_PR_TEST_ISSUE=123 uv run pytest tests/test_tracker.py -k live_draft_pr_publish -rs
```

## 2. 대상 저장소 초기화

```bash
cd /path/to/your/repo
uv run repoagents init
uv run repoagents init --preset python-library --tracker-repo owner/name
uv run repoagents init --tracker-kind local_file --tracker-path issues.json
uv run repoagents doctor
uv run repoagents ops snapshot --archive
uv run repoagents ops snapshot --archive --history-limit 5 --prune-history
uv run repoagents ops status
cat .ai-repoagents/reports/ops/latest.json
```

`uv run repoagents init`을 플래그 없이 실행하면 대화형 초기화가 시작됩니다. GitHub 없이 로컬 JSON inbox로만 돌리려면 `--tracker-kind local_file`를 사용하면 됩니다. 라이브 Codex 세션 없이 오프라인 walkthrough를 하고 싶다면 저장소에 포함된 demo script가 결정적인 fake `codex` shim을 자동으로 설치합니다.

생성되는 제어 파일:

- `.ai-repoagents/repoagents.yaml`
- `.ai-repoagents/roles/*`
- `.ai-repoagents/prompts/*`
- `.ai-repoagents/policies/*`
- `AGENTS.md`
- `WORKFLOW.md`

나중에 로컬 수정 보존 상태로 managed template drift를 점검하려면:

```bash
uv run repoagents init --upgrade
uv run repoagents init --upgrade --force
```

## 3. 로컬 결정적 데모 실행

빠른 경로:

```bash
bash scripts/demo_python_lib.sh
bash scripts/demo_local_file_tracker.sh
bash scripts/demo_live_ops.sh
bash scripts/release_preflight.sh
```

추가 runnable demo:

<details>
<summary>전체 데모 매트릭스</summary>

```bash
bash scripts/demo_web_app.sh
bash scripts/demo_local_file_sync.sh
bash scripts/demo_local_markdown_tracker.sh
bash scripts/demo_local_markdown_sync.sh
bash scripts/demo_qa_role_pack.sh
bash scripts/demo_webhook_receiver.sh
bash scripts/demo_webhook_signature_receiver.sh
bash scripts/demo_live_publish_sandbox.sh
bash scripts/demo_release_rehearsal.sh
bash scripts/demo_release_publish_dry_run.sh
```

</details>

이 스크립트들은 예제 저장소를 임시 작업 디렉터리로 복사해서, 체크인된 예제 파일을 건드리지 않고 데모를 재현합니다.

`bash scripts/demo_live_ops.sh`는 이제 청사진만 준비하는 수준을 넘어서 `github smoke`를 rehearse하고, `ops snapshot` handoff bundle과 archive를 만들고, `ops-status`를 갱신하며, 읽기 순서는 `examples/live-github-ops/ops/handoff-order.md`에 고정해 둡니다.

`bash scripts/demo_live_publish_sandbox.sh`는 그 다음 단계입니다. `baseline -> comments-ready -> pr-gated -> pr-ready` 순서로 rollout을 rehearse하고, phase report를 `.ai-repoagents/reports/sandbox-rollout/` 아래에 남기고, branch-policy gate가 열리기 전에는 `github smoke --require-write-ready`가 실패하고 열린 뒤에는 통과한다는 것을 보여준 다음 sandbox readiness bundle을 `.ai-repoagents/reports/ops/sandbox-pr-ready/` 아래에 만들고, 이어서 deterministic issue 하나를 실행한 execution bundle을 `.ai-repoagents/reports/ops/sandbox-issue-201/` 아래에 남깁니다.

`bash scripts/demo_release_rehearsal.sh`는 현재 저장소를 disposable workspace로 복사한 뒤 `release preview`, `release announce` artifact를 만들고, local annotated rehearsal tag를 생성하고, `uv build`를 돌린 뒤 tag/build evidence를 `.ai-repoagents/reports/release-rehearsal/` 아래에 남깁니다.

`bash scripts/demo_release_publish_dry_run.sh`는 그 다음 release 단계를 rehearse합니다. disposable workspace를 inferred preview version으로 맞추고, local annotated rehearsal tag를 만들고, `repoagents release assets --build --smoke-install --format all`을 실행하고, publish-ready checksum과 upload command evidence를 `.ai-repoagents/reports/release-publish-dry-run/` 아래에 남깁니다.

disposable demo가 아니라 실제 저장소에서 배포 직전 gate를 한 번에 돌리고 싶다면 아래 wrapper를 사용하면 됩니다.

```bash
bash scripts/release_preflight.sh
```

이 스크립트는 `repoagents release check --format all`을 실행해서 release preview, announcement copy pack 생성, `uv run pytest -q`, `uv build`, wheel smoke install, OSS governance/CI 체크를 한 번에 수행합니다.

```bash
cd examples/python-lib
uv run repoagents init --preset python-library --fixture-issues issues.json --tracker-repo demo/python-lib
uv run --project /path/to/RepoAgents python -m repoagents.testing.fake_codex \
  --install-shim .ai-repoagents/demo-bin/codex \
  --project-root /path/to/RepoAgents
python3 - <<'PY'
from pathlib import Path
import yaml
path = Path(".ai-repoagents/repoagents.yaml")
payload = yaml.safe_load(path.read_text())
payload["codex"]["command"] = str((Path(".ai-repoagents/demo-bin/codex")).resolve())
path.write_text(yaml.safe_dump(payload, sort_keys=False))
PY
uv run repoagents run --dry-run
uv run repoagents run --once
uv run repoagents status
uv run repoagents dashboard
uv run repoagents dashboard --tui
uv run repoagents ops snapshot --include-cleanup-preview --include-cleanup-result --include-sync-check --include-sync-repair-preview --archive
uv run repoagents ops status --format all
cat .ai-repoagents/reports/ops/history.json
```

`ops snapshot` history retention 기본값은 `cleanup.ops_snapshot_keep_entries`입니다. dropped managed bundle/archive를 `.ai-repoagents/reports/ops/` 아래에서 함께 정리하고 싶을 때만 `--prune-history`를 사용하면 됩니다.
dashboard를 열지 않고 최신 indexed handoff bundle, recent history, 현재 handoff brief headline, landing path, 그리고 최신 bundle이 참조한 `sync-health` / `sync-audit` posture와 live GitHub REST tracker일 때의 `github-smoke` posture까지 한 번에 확인하려면 `ops status`를 사용하면 됩니다.

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

publish-enabled sandbox rollout을 단계적으로 rehearse하려면 아래 예제를 사용하면 됩니다.

```bash
cd examples/live-github-sandbox-rollout
bash ../../scripts/demo_live_publish_sandbox.sh
```

무슨 일이 일어나는지:

1. RepoAgents가 GitHub tracker adapter의 fixture mode로 issue를 읽습니다.
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
uv run repoagents init --preset python-library --tracker-kind local_file --tracker-path issues.json
uv run repoagents trigger 1
uv run repoagents dashboard
```

```bash
cd examples/local-file-sync
bash ../../scripts/demo_local_file_sync.sh
```

```bash
cd examples/local-markdown-inbox
uv run repoagents init --preset python-library --tracker-kind local_markdown --tracker-path issues
uv run repoagents trigger 1
uv run repoagents dashboard
```

```bash
cd examples/local-markdown-sync
bash ../../scripts/demo_local_markdown_sync.sh
```

이 경로는 tracker는 오프라인으로 유지하면서 publish 제안을 `.ai-repoagents/sync/local-markdown/issue-1/` 아래에 stage합니다.
`uv run repoagents sync ls --issue 1`로 staged inventory를 보고, `uv run repoagents sync show ...`로 proposal 하나를 열 수 있습니다.
`uv run repoagents sync apply --issue 1 --tracker local-markdown --action comment --latest`를 실행하면 최신 comment proposal이 원본 Markdown issue에 반영되고, 처리된 artifact는 `.ai-repoagents/sync-applied/`로 이동합니다.
`uv run repoagents sync apply --issue 1 --tracker local-markdown --action pr-body --latest --bundle`을 실행하면 관련 branch/PR handoff set을 한 번에 archive할 수 있습니다.
같은 JSON inbox 경로에서는 `uv run repoagents sync apply --issue 1 --tracker local-file --action comment --latest`를 사용하면 됩니다.
`uv run repoagents sync check --issue 1`로 applied manifest 무결성을 확인하고, `uv run repoagents sync repair --issue 1 --dry-run`으로 canonicalize/adopt 결과를 미리 볼 수 있습니다.
`uv run repoagents sync health --issue 1 --format all`은 `sync check`, `sync repair`, `clean`로 들어가기 전에 sync 운영 상태를 한 번에 묶어서 보여줍니다.
오래된 applied handoff group을 지우기 전에는 `uv run repoagents clean --sync-applied --dry-run`으로 manifest-aware retention 결과를 먼저 확인합니다.
`uv run repoagents dashboard --tui`를 실행하면 터미널 안에서 `Sync handoffs`, `Sync retention`, prunable group 수, prunable bytes, oldest prunable age를 함께 볼 수 있습니다. 자동 새로고침이 필요하면 `--refresh-seconds 30`을 붙이면 됩니다. TUI 안에서는 `Runs`나 `Reports` 항목을 선택한 뒤 `a`를 눌러 그 행에서 가능한 작업 메뉴를 열 수 있습니다.
같은 상위 상태를 터미널 안에서 바로 보고 싶다면 `uv run repoagents dashboard --tui`를 사용하면 됩니다.

## 4. 운영 모드로 전환

`.ai-repoagents/repoagents.yaml`을 수정합니다.

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

그 다음 GitHub 인증을 준비하고 polling을 시작합니다.

```bash
gh auth login
uv run repoagents doctor
uv run repoagents github smoke --require-write-ready
uv run repoagents run
```

`GITHUB_TOKEN`이 비어 있으면 RepoAgents가 자동으로 `gh auth token`을 재사용합니다. 환경변수를 명시적으로 두고 싶거나 CI를 설정하는 경우에는 `export GITHUB_TOKEN="$(gh auth token)"`처럼 설정하면 됩니다.

이제 `github smoke --require-write-ready`는 unattended draft PR publish를 켜기 전에 default branch protection, PR review requirement, required status check, repo metadata push permission까지 함께 확인합니다.

polling 대신 event-driven으로 실행하려면:

```bash
uv run repoagents trigger 123 --dry-run
uv run repoagents webhook --event issues --payload webhook.json --dry-run
```

## 5. 결과 확인

- artifact: `.ai-repoagents/artifacts/issue-<id>/<run-id>/`
- debug artifact 활성화 시: `<role>.prompt.txt`, `<role>.raw-output.txt`
- workspace: `.ai-repoagents/workspaces/issue-<id>/<run-id>/repo/`
- run state: `.ai-repoagents/state/runs.json`
- dashboard Markdown snapshot: `.ai-repoagents/dashboard/index.md`
- dashboard JSON snapshot: `.ai-repoagents/dashboard/index.json`
- sync audit reports: `.ai-repoagents/reports/sync-audit.json`, `.ai-repoagents/reports/sync-audit.md`
- sync health reports: `.ai-repoagents/reports/sync-health.json`, `.ai-repoagents/reports/sync-health.md`
- ops brief snapshots: `.ai-repoagents/reports/ops-brief.json`, `.ai-repoagents/reports/ops-brief.md`
- bundle landing files: `.ai-repoagents/reports/ops/<timestamp>/index.html`, `.ai-repoagents/reports/ops/<timestamp>/README.md`
- cleanup reports: `.ai-repoagents/reports/cleanup-preview.json`, `.ai-repoagents/reports/cleanup-result.json`
- doctor snapshots: `.ai-repoagents/reports/doctor.json`, `.ai-repoagents/reports/doctor.md`
- status snapshots: `.ai-repoagents/reports/status.json`, `.ai-repoagents/reports/status.md`
- release preview snapshots: `.ai-repoagents/reports/release-preview.json`, `.ai-repoagents/reports/release-preview.md`
- GitHub release notes preview: `.ai-repoagents/reports/release-notes-v<version>.md`
- release announcement pack: `.ai-repoagents/reports/release-announce.json`, `.ai-repoagents/reports/release-announce.md`
- release checklist: `.ai-repoagents/reports/release-checklist.json`, `.ai-repoagents/reports/release-checklist.md`
- channel copy snippets: `.ai-repoagents/reports/announcement-v<version>.md`, `discussion-v<version>.md`, `social-v<version>.md`, `release-cut-v<version>.md`
- release asset report: `.ai-repoagents/reports/release-assets.json`, `.ai-repoagents/reports/release-assets.md`
- release asset summary: `.ai-repoagents/reports/release-assets-v<tag>.md`
- 선택적 JSONL 로그: `.ai-repoagents/logs/repoagents.jsonl`
- 특정 이슈 상태: `uv run repoagents status --issue 123`
- operator health snapshot export: `uv run repoagents doctor --format all`, `uv run repoagents status --format all`
- 다음 public tag cut preview: `uv run repoagents release preview --format all`
- release copy pack 생성: `uv run repoagents release announce --format all`
- 전체 release preflight gate 실행: `uv run repoagents release check --format all`
- local release asset 검증: `uv run repoagents release assets --build --smoke-install --format all`
- 특정 이슈 즉시 실행: `uv run repoagents trigger 123`
- repo-local background worker 시작: `uv run repoagents service start`
- background worker 상태 확인: `uv run repoagents service status`
- 설정 변경이나 lease takeover 이후 background worker 재시작: `uv run repoagents service restart`
- background worker 종료 요청: `uv run repoagents service stop`
- approval inbox 확인: `uv run repoagents approval ls`
- 특정 approval request 확인: `uv run repoagents approval show 123`
- maintainer 승인 결정 기록: `uv run repoagents approval approve 123 --reason "ready for manual publish"`
- GitHub webhook payload 검증: `uv run repoagents webhook --event issues --payload webhook.json --dry-run`
- 다음 poll cycle용 재시도 큐에 넣기: `uv run repoagents retry 123`
- 오래된 local 정리 미리보기: `uv run repoagents clean --dry-run`
- applied sync archive 정리 미리보기: `uv run repoagents clean --sync-applied --dry-run`
- cleanup preview/report export: `uv run repoagents clean --sync-applied --dry-run --report --report-format all`
- applied manifest 무결성 검사: `uv run repoagents sync check --issue 123`
- applied manifest repair 미리보기: `uv run repoagents sync repair --issue 123 --dry-run`
- combined sync-ops snapshot export: `uv run repoagents sync health --issue 123 --format all`
- sync audit bundle export: `uv run repoagents sync audit --format all`
- 로컬 대시보드 다시 생성: `uv run repoagents dashboard`
- 자동 새로고침이 있는 터미널 대시보드 열기: `uv run repoagents dashboard --tui --refresh-seconds 30`
- JSON과 Markdown을 함께 export: `uv run repoagents dashboard --format all`

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
