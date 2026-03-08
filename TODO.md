# TODO

RepoRepublic MVP 이후 구현할 우선순위 backlog입니다. 현재 코드는 로컬 데모와 mock backend 기준으로는 동작하지만, 실운영 완성도를 높이려면 아래 항목이 필요합니다.

## P0. 운영 경로 완성

- [x] Git branch 생성과 PR 오픈 경로 구현
  - 현재 `create_branch`와 `open_pr`는 보수적으로 막혀 있음
  - GitHub 이슈 처리 후 실제 브랜치를 만들고 PR 초안을 여는 안전한 경로 필요
  - 완료 기준: 설정이 허용할 때만 브랜치/PR이 생성되고, dry-run에서는 항상 차단됨

- [x] engineer 결과와 실제 diff를 연결한 PR 본문/코멘트 생성
  - 지금은 결과 요약과 변경 파일이 분리되어 있음
  - `patch_summary`, 테스트 결과, reviewer 요약을 합친 표준 템플릿 필요
  - 완료 기준: 이슈 코멘트/PR 본문이 일관된 Markdown 형식으로 생성됨

- [x] GitHub REST adapter pagination과 오류 복구 강화
  - open issues가 많을 때 현재 구현은 단일 페이지 위주
  - rate limit, 403/429, 네트워크 재시도 처리 보강 필요
  - 완료 기준: pagination, timeout, backoff, rate-limit 로그가 포함됨

- [x] 실제 Codex 실행 경로에 대한 end-to-end 통합 테스트 추가
  - 지금 테스트는 command builder 위주
  - Codex가 설치된 환경에서만 opt-in으로 도는 smoke test가 필요
  - 완료 기준: `CODEX_E2E=1` 같은 플래그로 비파괴 통합 테스트 실행 가능

## P1. 워크스페이스와 실행 안정성

- [x] `git worktree` 기반 workspace 전략 추가
  - 현재는 copy 전략만 지원
  - 대형 저장소에서는 copy 비용이 큼
  - 완료 기준: `workspace.strategy: worktree` 선택 시 분리된 worktree 사용 가능

- [x] dirty working tree 감지와 운영 정책 추가
  - 현재는 원본 저장소가 변경된 상태여도 copy를 뜸
  - 실운영에서는 기준점이 불명확해질 수 있음
  - 완료 기준: dirty 상태 감지, 경고, 차단 또는 허용 정책이 설정 가능

- [x] run status / retry / clean 운영 명령 확장
  - `status --issue`, `retry`, `clean` 명령이 추가됨
  - 특정 issue 강제 재실행과 stale local run data 정리가 가능함

- [x] state schema versioning 도입
  - `runs.json`에 버전 필드와 migration 경로가 추가됨
  - legacy payload도 현재 스키마로 자동 마이그레이션함

- [x] structured logging 파일 출력 지원
  - `logging.file_enabled: true`일 때 `.ai-republic/logs/reporepublic.jsonl`에 JSONL 로그를 남김
  - run/issue 문맥이 로그 레코드에 포함됨

## P1. 역할 품질 개선

- [x] triage duplicate 후보 탐지 고도화
  - open issue 제목/본문/label 유사도를 합쳐 duplicate 후보를 랭킹함
  - triage prompt에는 score와 overlap term이 포함된 후보 힌트를 넣고, mock backend도 같은 힌트를 사용함
  - 동일/유사 이슈를 confidence와 함께 표시함

- [x] planner의 repo context 수집 개선
  - 단순 파일 목록 대신 top-level 디렉터리, 테스트 구조, 최근 git 변경 파일을 함께 요약함
  - README 발췌와 파일 샘플은 유지하되 전체 컨텍스트 길이는 잘라서 제어함
  - planner prompt에 더 유의미한 저장소 요약이 포함됨

- [x] reviewer의 diff 해석 강화
  - reviewer는 diff에서 review signal을 만들고 테스트 부족, 범위 이탈, 패치 크기를 함께 해석함
  - mock reviewer와 reviewer prompt 모두 이 signal을 사용함

- [x] request_changes 기준 추가 정교화
  - reviewer는 policy findings, 테스트 없는 코드 변경, planner 범위 이탈 + manual-only validation 같은 must-fix 조건을 명시적으로 계산함
  - mock reviewer와 orchestrator override가 같은 기준을 공유해 Codex 출력도 보정함

- [x] role별 artifact 포맷 확장
  - `agent.debug_artifacts: true`일 때 role별 raw prompt와 raw backend output을 artifact에 함께 저장함
  - 기본 모드에서는 기존 JSON + Markdown 아티팩트만 유지함

## P1. 안전장치 강화

- [x] 민감 파일 탐지 규칙 확장
  - `.github/workflows`, infra/deploy/auth 관련 경로와 token/credential 계열 이름을 더 넓게 감지함
  - 정책 엔진은 `PolicyRules`로 repo별 규칙 주입을 지원함

- [x] 대규모 삭제/이동 감지 정확도 개선
  - rename/move 유사 패턴과 generated/vendor 경로를 고려해 false positive를 줄임
  - 정책 테스트로 회귀를 고정함

- [x] human approval 정책 세분화
  - `merge_policy.mode`에 `comment_only`, `draft_pr`, `human_approval`를 추가함
  - low-risk docs/tests 변경은 설정에 따라 comment-only 또는 draft PR publish 경로를 탈 수 있음

## P2. 개발자 경험

- [x] `republic init` 대화형 모드 추가
  - 플래그 없이 실행하면 preset, tracker repo, backend mode, fixture path를 순서대로 안내함
  - `--backend`와 비대화형 플래그 경로도 계속 지원함

- [x] `republic doctor` 진단 항목 확장
  - GitHub auth, network reachability, template drift, write 권한 점검이 추가됨
  - 실패 원인과 해결 힌트를 더 구체적으로 출력함

- [x] `republic init --upgrade` 또는 템플릿 drift 감지
  - `republic init --upgrade`는 drift를 보여주고 missing managed 파일을 복구함
  - `republic init --upgrade --force`는 drifted managed 파일까지 refresh함

- [x] examples 실행 스크립트 제공
  - `scripts/demo_python_lib.sh`, `scripts/demo_web_app.sh`로 임시 작업 디렉터리에서 예제를 재현 가능
  - 문서와 실제 스크립트 경로를 맞춤

- [x] 문서 다국어 구조 정리
  - 루트 README와 docs 인덱스에서 영문/국문 진입점을 함께 제공함
  - `name.md` / `name.ko.md` 규칙과 신규 문서 추가 규칙을 문서화함

- [x] 운영 runbook 문서 추가
  - `docs/runbook.md`, `docs/runbook.ko.md`에 day-2 운영 절차를 정리함
  - `doctor`, `status`, `retry`, `trigger`, `webhook`, `dashboard`, `clean` 경로를 incident 대응 기준으로 문서화함

- [x] tracker adapter 예제 확장
  - `examples/local-file-inbox`와 `scripts/demo_local_file_tracker.sh`를 추가해 `local_file` tracker 경로를 바로 재현할 수 있음
  - 기존 GitHub fixture 예제와 함께 tracker mode 차이를 문서화함

- [x] role pack 예제 추가
  - `docs/role-packs.md`, `docs/role-packs.ko.md`에 optional built-in role pack 예제를 정리함
  - `examples/qa-role-pack`와 `scripts/demo_qa_role_pack.sh`로 `qa` role pack 경로를 runnable demo로 제공함

- [x] webhook receiver server 예제 추가
  - `scripts/webhook_receiver.py`로 GitHub 스타일 POST를 `republic webhook`으로 포워딩하는 로컬 HTTP receiver 예제를 추가함
  - `examples/webhook-receiver`와 `scripts/demo_webhook_receiver.sh`로 end-to-end 데모를 제공함

- [x] live deployment/ops examples 추가
  - `examples/live-github-ops`와 `scripts/demo_live_ops.sh`로 GitHub REST 운영 청사진을 runnable demo로 제공함
  - `worktree`, 파일 로그, timed reload dashboard, ops helper 파일을 함께 예시화함

- [x] live GitHub operations walkthrough 추가
  - `docs/live-github-ops.md`, `docs/live-github-ops.ko.md`에 실제 저장소 기준의 단계별 운영 절차를 정리함
  - 초기화, doctor, 단일 issue dry-run/trigger, loop 기동, dashboard, failure handling, rollout 순서를 문서화함

- [x] additional custom role pack examples 추가
  - `examples/docs-maintainer-pack`와 `scripts/demo_docs_maintainer_pack.sh`로 repo-local override pack 예제를 추가함
  - 새 runtime role 없이도 role/prompt/policy/AGENTS override만으로 custom maintainer pack을 구성하는 경로를 문서화함

- [x] webhook auth/signature verification example 추가
  - `scripts/webhook_receiver.py`에 선택적 shared secret 기반 `X-Hub-Signature-256` 검증 경로를 추가함
  - `examples/webhook-signature-receiver`와 `scripts/demo_webhook_signature_receiver.sh`로 signed webhook receiver 데모를 제공함

- [x] dashboard export/share formats 추가
  - `republic dashboard --format html|json|markdown|all` 경로를 추가해 HTML 외 export를 지원함
  - live ops helper와 문서에 JSON/Markdown snapshot 공유 경로를 연결함

- [x] additional tracker vendors/examples 추가
  - `local_markdown` tracker를 추가해 Markdown issue 디렉터리를 read-only inbox로 읽을 수 있게 함
  - `examples/local-markdown-inbox`와 `scripts/demo_local_markdown_tracker.sh`로 runnable demo를 제공함

- [x] additional custom tracker write paths or sync adapters 추가
  - `local_markdown` tracker가 `.ai-republic/sync/local-markdown/issue-<id>/` 아래에 comment, branch, label, draft PR proposal을 stage할 수 있게 함
  - `examples/local-markdown-sync`와 `scripts/demo_local_markdown_sync.sh`로 runnable demo를 제공함

- [x] tracker sync artifact export/apply utility 추가
  - `republic sync ls`와 `republic sync show`로 staged sync artifact inventory를 조회할 수 있게 함
  - 공통 sync contract를 `docs/sync.md`, `docs/sync.ko.md`에 문서화함

- [x] tracker-specific sync apply helpers 추가
  - `republic sync apply`로 `local_markdown` comment/labels artifact를 source issue에 반영하고 handled artifact를 `.ai-republic/sync-applied/`로 archive함
  - `sync ls --scope applied`와 demo/runbook 문서로 apply 이후 lifecycle을 확인할 수 있게 함

- [x] `branch`/`pr-body` artifact bundle apply helper 추가
  - `republic sync apply --bundle`로 관련 `branch`, `pr`, `pr-body` handoff set을 한 번에 archive할 수 있음
  - `local_markdown` sync demo와 CLI 테스트가 bundle helper 경로를 검증함

- [x] tracker별 sync apply/export를 위한 pluggable action registry 정리
  - `SyncActionRegistry`로 tracker/action별 apply handler와 tracker-level bundle resolver를 등록할 수 있음
  - custom registry 주입 테스트로 extension seam을 고정함

- [x] sync artifact naming/link metadata를 provider-neutral하게 정규화
  - `SyncArtifact.normalized`에 `artifact_role`, `issue_key`, `bundle_key`, `refs`, `links`를 추가함
  - CLI와 manifest가 같은 normalized schema를 노출함

- [x] sync artifact manifest에 richer handoff linkage 추가
  - manifest entry에 `entry_key`, `archived_relative_path`, `handoff.group_*`, `related_*`를 기록함
  - singleton apply와 bundle apply가 같은 linkage schema를 사용함

## P2. 테스트 확장

- [x] live GitHub adapter 테스트 추가
  - fixture mode 외 live mode 테스트가 없음
  - 완료 기준: 토큰이 있을 때만 실행되는 opt-in integration test 추가

- [x] failure-path 테스트 보강
  - Codex timeout, malformed JSON, tracker 5xx, retry exhaustion 시나리오 추가 필요
  - 완료 기준: 주요 예외 경로가 테스트로 고정됨

- [x] policy evaluation 단위 테스트 추가
  - 현재 직접 테스트가 없음
  - 완료 기준: secrets/CI/auth/large deletion 케이스를 모두 검증

- [x] scaffold snapshot 테스트 추가
  - `republic init`이 생성하는 파일이 의도치 않게 바뀌지 않도록 해야 함
  - 완료 기준: preset별 생성 결과 스냅샷 검증

## P3. 확장성과 운영 기능

- [x] 다중 tracker adapter 준비
  - tracker factory가 `github`와 `local_file` 구현체를 registry 방식으로 선택함
  - `local_file` adapter로 로컬/오프라인 issue inbox를 실제로 실행할 수 있음

- [x] 역할 확장 시스템
  - role registry와 설정 기반 순서 정의를 추가했고, optional built-in `qa` role을 `engineer`와 `reviewer` 사이에 연결할 수 있음
  - 이후 `security-review`, `docs-editor`, `release-manager` 같은 추가 role도 같은 경로로 확장 가능

- [x] webhook 또는 event-driven 실행 모드
  - `republic trigger <issue-id>`로 polling 없이 단일 issue run/dry-run을 시작할 수 있음
  - `republic webhook --event issues --payload payload.json`으로 GitHub webhook payload를 받아 단일 issue run을 시작할 수 있음

- [x] 장기적으로 웹 UI 또는 운영 대시보드
  - `republic dashboard`가 현재 run 상태, artifact 링크, 실패 사유를 정적 HTML로 생성함
  - 기본 출력은 `.ai-republic/dashboard/index.html`

- [x] dashboard filtering/search와 live refresh 추가
  - 대시보드에 client-side 검색, 상태 필터, 빈 결과 메시지를 추가함
  - `republic dashboard --refresh-seconds <n>`으로 timed reload 기본값을 심을 수 있음

- [x] dashboard/export에 normalized sync metadata 링크 연결
  - dashboard가 `.ai-republic/sync-applied/**/manifest.json`을 읽어 `Sync handoffs` 섹션을 함께 렌더링함
  - HTML/JSON/Markdown export가 manifest, archived artifact, normalized link target을 함께 노출함

- [x] sync artifact cleanup/retention 정책을 manifest-aware하게 정리
  - `republic clean --sync-applied`가 `handoff.group_key` 단위 retention을 적용함
  - orphan archive 파일과 dangling manifest entry도 함께 보수적으로 정리함

## 추천 다음 순서

1. applied sync manifest integrity 검사와 repair helper 추가
2. sync-applied retention 결과를 dashboard에 age/size 기준으로 시각화
