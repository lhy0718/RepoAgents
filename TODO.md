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

- [x] applied sync manifest integrity 검사와 repair helper 추가
  - `republic sync check`가 duplicate key, dangling archive, orphan file, handoff mismatch를 보고함
  - `republic sync repair`가 canonicalize, orphan adoption, handoff linkage 재구성을 수행함

- [x] sync-applied retention 결과를 dashboard에 age/size 기준으로 시각화
  - `republic dashboard`가 `Sync retention` 섹션에서 issue별 `stable/prunable/repair-needed` 상태를 노출함
  - JSON/Markdown export도 prunable group 수, bytes, oldest prunable age를 함께 남김

- [x] sync audit report export 추가
  - `republic sync audit --format all`이 `.ai-republic/reports/` 아래에 JSON/Markdown report를 생성함
  - report가 pending inventory, applied manifest integrity, retention summary를 한 번에 묶어줌

- [x] sync-applied cleanup 결과를 machine-readable report로 남기기
  - `republic clean --sync-applied --dry-run --report`가 cleanup preview/result를 `.ai-republic/reports/` 아래에 저장함
  - report가 action list, affected issue, manifest rewrite count를 남김

- [x] sync audit / cleanup report를 dashboard에서 바로 열 수 있게 연결
  - `republic dashboard`가 `.ai-republic/reports/`를 읽어 `Reports` 섹션과 HTML/JSON/Markdown report summary를 함께 렌더링함
  - sync audit/cleanup export가 있을 때 dashboard에서 직접 링크와 상태 요약을 확인할 수 있음

- [x] cleanup report를 sync audit에 cross-link
  - `republic sync audit` snapshot이 matching `cleanup-preview` / `cleanup-result` export를 읽어 함께 요약함
  - JSON/Markdown export와 CLI 출력이 linked cleanup report 수를 노출함

- [x] applied sync manifest integrity 요약을 dashboard report card에서 더 자세히 표시
  - dashboard `Reports` 섹션의 `Sync audit` card가 finding count, clean/issues split, affected issue sample을 함께 보여줌
  - dashboard JSON/Markdown export도 같은 integrity detail을 report entry에 포함함

- [x] sync audit linked cleanup report를 dashboard report card와 교차 참조
  - `Sync audit` card가 linked cleanup report card로 바로 이동할 수 있음
  - cleanup report card는 `Sync audit`에 의해 참조되고 있음을 함께 표시함

- [x] report card에서 integrity finding code를 action-oriented hint로 요약
  - `Sync audit` card가 `missing_manifest`, `duplicate_entry_key` 같은 finding code를 운영 액션으로 번역함
  - dashboard JSON/Markdown export도 같은 hint를 report detail에 포함함

- [x] sync audit related cleanup report에 issue filter mismatch 경고 추가
  - `republic sync audit --issue <id>`가 다른 `issue_filter`로 생성된 cleanup report를 mismatch warning으로 분리해 보여줌
  - JSON/Markdown export와 CLI 출력이 mismatch count를 함께 노출함

- [x] dashboard report card에 cleanup report freshness/age 표시 추가
  - cleanup report card가 `freshness_status`와 사람이 읽기 쉬운 `age`를 함께 보여줌
  - dashboard JSON/Markdown export도 같은 freshness/age 필드를 포함함

- [x] sync audit mismatch warning을 dashboard `Sync audit` card에도 반영
  - `Sync audit` card가 linked cleanup report의 issue filter mismatch warning을 detail과 metric으로 함께 보여줌
  - dashboard JSON/Markdown export도 같은 mismatch warning과 count를 포함함

- [x] cleanup report freshness를 dashboard summary metric으로 집계
  - `Reports` summary metric이 cleanup report들의 `fresh/aging/stale` 집계를 함께 보여줌
  - dashboard snapshot과 JSON/Markdown export도 같은 freshness 집계를 포함함

- [x] stale report 집계를 dashboard summary card로 분리
  - `Reports` metric row에 `Stale cleanup reports` 카드가 별도로 표시됨
  - dashboard snapshot과 JSON/Markdown export도 stale cleanup report count를 함께 남김

- [x] report freshness를 전체 report 기준으로도 집계
  - `Reports` metric row에 전체 report 기준 `Report freshness` aggregate가 추가됨
  - dashboard snapshot과 JSON/Markdown export도 전체 report freshness 집계를 포함함

- [x] aging report 집계를 dashboard summary card로 분리
  - `Reports` metric row에 `Aging reports` 카드가 별도로 표시됨
  - dashboard snapshot과 JSON/Markdown export도 aging report count를 함께 남김

- [x] future report 집계를 dashboard summary card로 분리
  - `Reports` metric row에 `Future reports` 카드가 별도로 표시됨
  - dashboard snapshot과 JSON/Markdown export도 future report count를 함께 남김

- [x] unknown report freshness를 dashboard warning metric으로 분리
  - `Reports` metric row에 `Unknown freshness reports` warning card가 조건부로 표시됨
  - dashboard snapshot과 JSON/Markdown export도 unknown report count를 함께 남김

- [x] cleanup aging report 집계를 dashboard summary card로 분리
  - `Reports` metric row에 `Cleanup aging reports` 카드가 표시됨
  - dashboard snapshot과 JSON/Markdown export도 cleanup aging report count를 함께 남김

- [x] cleanup future report 집계를 dashboard summary card로 분리
  - `Reports` metric row에 `Cleanup future reports` 카드가 표시됨
  - dashboard snapshot과 JSON/Markdown export도 cleanup future report count를 함께 남김

- [x] cleanup unknown freshness를 dashboard warning metric으로 분리
  - `Reports` metric row에 `Cleanup unknown freshness reports` warning card가 조건부로 표시됨
  - dashboard snapshot과 JSON/Markdown export도 cleanup unknown report count를 함께 남김

- [x] report freshness aggregate를 alert severity와 연결
  - `Report freshness`, `Cleanup freshness` card가 `issues/attention/clean` severity와 reason을 함께 가짐
  - dashboard snapshot과 JSON/Markdown export도 같은 severity metadata를 포함함

- [x] report freshness aggregate에 repo policy threshold를 연결
  - `dashboard.report_freshness_policy`로 severity threshold를 repo별로 조정할 수 있음
  - threshold override는 overall/cleanup freshness severity 계산에 함께 반영됨

- [x] report freshness severity를 dashboard hero summary와 연결
  - hero banner가 overall/cleanup freshness severity 중 더 높은 수준을 반영함
  - hero summary와 JSON/Markdown snapshot이 title/reason/chip 형태로 report health를 함께 노출함

- [x] doctor에 report freshness policy 진단을 추가
  - `republic doctor`가 현재 threshold를 그대로 출력함
  - stale/unknown escalation이 과도하게 완화된 경우 WARN과 hint를 함께 보여줌

- [x] report freshness severity를 `republic status` export와 연결
  - `republic status`가 dashboard와 같은 report-health snapshot을 읽어 severity를 함께 출력함
  - overall/cleanup freshness reason이 run state 출력 옆에서 바로 확인 가능함

- [x] report freshness policy를 dashboard/export metadata에 명시적으로 남기기
  - dashboard snapshot JSON/Markdown이 현재 `report_freshness_policy` threshold를 함께 기록함
  - HTML dashboard도 같은 policy summary를 meta chip으로 보여줌

- [x] report freshness policy를 report card detail에도 직접 노출하기
  - 각 report entry가 동일한 policy summary와 threshold를 own detail payload에 포함함
  - HTML/Markdown report card view에서도 per-report policy context를 바로 확인 가능함

- [x] status 출력에도 policy threshold summary를 함께 붙이기
  - `republic status`가 report health summary 바로 아래에 current policy summary를 출력함
  - severity와 escalation baseline을 CLI 한 화면에서 같이 확인 가능함

- [x] sync audit/cleanup raw export에도 policy metadata를 직접 심기
  - raw sync audit / cleanup JSON export가 active policy threshold를 함께 기록함
  - Markdown export도 같은 policy summary를 별도 section으로 노출함

- [x] dashboard가 raw report의 embedded policy metadata drift를 감지하도록 하기
  - dashboard report card가 live policy와 embedded raw policy를 함께 비교함
  - `Policy drift reports` summary card와 JSON/Markdown snapshot count를 함께 노출함

- [x] raw report embedded policy mismatch를 sync audit/cleanup export metadata와 cross-link하기
  - raw `sync-audit` related cleanup entries가 `policy_alignment` metadata를 포함함
  - raw cleanup report도 latest `sync-audit` export를 같은 `policy_alignment` contract로 연결함

- [x] dashboard drift signal을 sync audit/cleanup related report section과 연결하기
  - dashboard `Cross references` panel이 related report의 policy drift note를 직접 표시함
  - cleanup/sync-audit card detail이 related report policy drift warning을 함께 담음

- [x] sync audit/cleanup related report policy drift를 CLI summary로 노출하기
  - `republic sync audit`가 linked cleanup policy drift count를 summary에 출력함
  - `republic clean --report`가 linked sync-audit policy drift count를 summary에 출력함

- [x] report policy drift를 dashboard hero/report summary severity와 연결
  - dashboard snapshot이 `report_summary_severity`와 `policy_drift_severity`를 별도로 기록함
  - dashboard hero와 `Report freshness` metric은 dashboard 전용 summary severity를 사용하고, drift-only 상황에서는 `Report policy drift needs follow-up`를 보여줌

- [x] report policy drift를 doctor/status policy health summary와 통합
  - `republic doctor`가 threshold relaxation과 embedded-policy drift를 합친 `Report policy health` summary를 출력함
  - `republic status`도 active threshold와 mismatch warning 옆에 같은 `policy_health` 요약을 출력함

- [x] report policy drift remediation guidance를 doctor/status/dashboard에서 공통 helper로 정리
  - `report_policy` helper가 drift remediation summary/detail 문구를 단일 source로 제공함
  - dashboard card, `republic doctor`, `republic status`가 같은 re-export guidance를 재사용함

- [x] report policy drift remediation guidance를 raw `sync-audit`/`cleanup` export 본문에도 직접 삽입
  - raw JSON의 related report `policy_alignment`와 drift summary entry에 `remediation`이 포함됨
  - raw Markdown export에도 `policy_remediation` / `remediation` 줄이 추가됨

- [x] sync audit/cleanup CLI summary에도 remediation guidance를 opt-in으로 직접 출력
  - `republic sync audit --show-remediation`과 `republic clean --report --show-remediation`이 drift가 있을 때 guidance를 출력함
  - 기본 summary 출력은 기존처럼 count 중심으로 유지됨

- [x] sync audit/cleanup CLI summary에 mismatch detail도 opt-in으로 직접 출력
  - `republic sync audit --show-mismatches`와 `republic clean --report --show-mismatches`가 linked report issue-filter mismatch warning을 직접 출력함
  - 기본 summary 출력은 count-only를 유지하고, detail은 opt-in으로만 노출함

- [x] report policy drift를 sync audit/cleanup CLI summary에서 mismatch detail과 함께 한 블록으로 정리
  - `--show-remediation`과 `--show-mismatches`를 함께 쓰면 related-report detail block 하나에 mismatch, drift, remediation이 같이 출력됨
  - `sync audit`와 `clean --report`가 같은 출력 구조를 재사용함

- [x] related-report detail block을 `doctor`/`status` 경고 출력에도 재사용
  - `Report policy export alignment`와 `policy_warning`가 같은 related-report detail block으로 drift warning과 remediation을 출력함
  - `policy_health`는 요약 역할만 유지하고 상세 drift listing은 block 쪽으로 정리함

- [x] related-report detail block을 dashboard report export markdown 요약과도 직접 맞춤
  - dashboard Markdown report entry에 `related_report_details` block을 추가해 CLI/doctor/status와 같은 읽기 흐름을 제공함
  - compact `details=` 요약은 유지하되, linked mismatch/drift/remediation은 별도 block으로도 노출함

- [x] dashboard HTML card의 Cross references 영역도 같은 block semantics를 더 직접적으로 드러냄
  - HTML report card가 `related report details` 아래에 `mismatches`와 `policy drifts` 섹션을 직접 렌더링함
  - policy drift가 있을 때 remediation guidance도 같은 패널에서 바로 보여줌

- [x] dashboard JSON export에도 related-report detail block의 presentation-oriented summary string 추가
  - 각 report entry에 `related_report_detail_summary`를 넣어 warning/remediation block을 평문으로 바로 재사용할 수 있게 함
  - structured `details`는 유지하고, display-oriented summary만 추가로 제공함

- [x] sync audit/cleanup raw export JSON에도 related-report detail summary string 추가
  - raw `related_reports` block에 `detail_summary`를 넣어 mismatch/drift/remediation 묶음을 평문으로 바로 재사용할 수 있게 함
  - structured `mismatches`, `policy_drifts`, `policy_alignment`는 그대로 유지함

- [x] related-report detail summary builder를 dashboard/raw export 경로 사이에서 공통 helper로 정리
  - dashboard, sync audit, cleanup report가 같은 formatter를 사용하게 해 drift 없이 유지보수 가능하게 함
  - 출력 포맷은 그대로 유지하고 pure helper 테스트를 추가함

- [x] related-report warning extraction helper도 dashboard/raw export 경로 사이에서 공통 helper로 정리
  - string list와 structured warning entry list를 같은 extractor로 처리하게 함
  - dashboard와 raw export가 같은 warning formatting 규칙을 재사용하게 함

- [x] related-report detail block markdown/html renderer를 공통 semantic block 기반으로 정리
  - CLI와 dashboard Markdown이 같은 line renderer를 사용하게 함
  - dashboard HTML도 같은 semantic block을 소비해 section label/내용 drift를 줄임

- [x] related-report detail block title/section label 정책을 공통 helper로 정리
  - `display`/`machine` 스타일을 분리해 surface별 title과 section label을 한 군데서 결정하게 함
  - CLI, dashboard Markdown, dashboard HTML이 같은 label policy를 공유하게 함

- [x] related-report remediation label과 section ordering 정책을 공통 helper로 정리
  - remediation label과 section order를 helper 상수/formatter로 끌어올려 surface별 drift를 줄임
  - dashboard HTML도 같은 remediation label policy를 subtitle로 사용함

- [x] related-report detail block spacing/list marker 정책을 공통 helper로 정리
  - line layout policy를 helper로 올려 CLI와 dashboard Markdown이 같은 spacing/list marker contract를 사용하게 함
  - title prefix, section indent, item marker, remediation line spacing을 한 군데서 관리하게 함

- [x] related-report detail block HTML subtitle/spacing 정책을 공통 helper로 정리
  - dashboard HTML이 subtitle margin과 remediation copy spacing을 semantic helper에서 가져오게 함
  - HTML block 구조는 유지하면서 subtitle/spacing drift를 한 군데서 관리하게 함

- [x] related-report detail block HTML class/tag policy를 공통 helper로 정리
  - subtitle/list/item/copy tag와 class 선택을 helper policy로 이동
  - dashboard HTML renderer가 `p/ul/li/p`를 직접 박지 않게 정리

- [x] related-report detail block HTML inline-style formatter를 공통 helper로 정리
  - subtitle/copy의 `margin-top` style attribute 조립을 helper로 이동
  - HTML renderer가 style 문자열을 직접 만들지 않게 정리

- [x] related-report detail block HTML escaping/attribute rendering helper를 공통화
  - text escaping과 class/style attribute 조립을 공통 helper로 이동
  - subtitle/copy/item renderer가 같은 HTML text-element helper를 사용하게 정리

- [x] related-report detail block HTML wrapper/list renderer를 더 generic helper로 정리
  - raw inner HTML을 감싸는 wrapper helper를 추가하고 list renderer가 이를 재사용하게 함
  - text element helper는 escaping만 맡고 wrapper helper 위에서 동작하게 정리

- [x] related-report detail block HTML helper를 private 내부 contract로 정리
  - HTML helper 이름을 underscore 내부 helper로 낮춰 외부 재사용 계약처럼 보이지 않게 정리
  - public 승격은 실제 두 번째 소비자가 생길 때 다시 판단

- [x] `report_policy.py` 내부 helper cluster를 섹션 주석으로 더 명확히 정리
  - public policy snapshot, related-report builder, label policy, private HTML helper 경계를 주석으로 나눔
  - 파일을 읽을 때 API 경계와 구현 세부사항을 빠르게 파악할 수 있게 정리

- [x] related-report detail helper cluster를 별도 internal submodule로 분리
  - `report_policy.py`는 policy snapshot/alignment만 남기고, related-detail 전용 로직은 internal module로 이동
  - dashboard/CLI/sync report 경로가 새 internal module을 직접 사용하게 정리

- [x] internal submodule 분리 후 test/module naming을 더 명확히 정리
  - related-detail 테스트를 `test_related_report_details.py`로 분리하고, `test_report_policy.py`는 policy-only 테스트로 재구성
  - 파일 이름이 실제 모듈 책임과 맞도록 정리

- [x] `_related_report_detail.py` 이름을 더 domain-specific하게 정리
  - internal submodule 이름을 `_related_report_details.py`로 맞춰 detail block cluster를 복수 개념으로 표현
  - 소비 경로와 테스트 import를 새 모듈명으로 일괄 정리

- [x] related-report internal module을 package로 분리
  - `_related_report_details/` 아래에 `models.py`, `rendering.py`, `html.py`, `__init__.py`로 책임을 나눔
  - import 표면은 `reporepublic._related_report_details`에서 유지하고 내부 구조만 정리

- [x] `_related_report_details` package root re-export 표면 축소
  - 소비자 import를 concrete submodule 직접 참조로 바꾸고, package root는 namespace marker 수준만 유지
  - internal package root가 공개 API처럼 보이지 않도록 정리

- [x] `doctor/status` operator snapshot export 추가
  - `--format json|markdown|all`, `--output`을 지원하고 `.ai-republic/reports/doctor.*`, `status.*` 기본 export 경로를 제공
  - terminal 요약과 별개로 운영 상태를 JSON/Markdown으로 공유·자동화 입력에 재사용할 수 있게 정리

- [x] `ops snapshot bundle` 작업 단위 구현
  - `doctor/status/dashboard/sync audit`를 한 디렉터리에 묶고 `bundle.json`, `bundle.md` manifest를 함께 생성
  - incident handoff와 automation 입력에 바로 쓸 수 있는 운영 번들 경로를 제공

- [x] `ops snapshot bundle`에 cleanup preview/result 선택 포함 추가
  - `--include-cleanup-preview`는 bundle 내부에 cleanup preview를 생성하고, `--include-cleanup-result`는 기존 cleanup result를 복사
  - bundle manifest가 cleanup component와 sync cross-link를 함께 기록하도록 확장

- [x] `ops snapshot bundle`에 sync check/repair preview 선택 포함 추가
  - `--include-sync-check`는 applied manifest integrity snapshot을 bundle 안에 생성함
  - `--include-sync-repair-preview`는 dry-run repair preview를 bundle 안에 생성하고 `sync-audit`/`sync-check`와 교차 링크함

- [x] `ops snapshot bundle` archive/tarball export 추가
  - `--archive`는 생성된 bundle directory를 `.tar.gz` handoff archive로 패킹함
  - CLI가 archive path, sha256, size, member count를 함께 출력함

- [x] `ops snapshot bundle` latest pointer/history index 추가
  - 매 `republic ops snapshot` 실행이 `.ai-republic/reports/ops/latest.*`, `history.*`를 갱신함
  - latest entry가 bundle/archive path와 component status를 함께 기록함

- [x] `ops snapshot bundle` history retention/prune policy 연결
  - `cleanup.ops_snapshot_keep_entries`와 `cleanup.ops_snapshot_prune_managed`를 `republic ops snapshot` 실행 경로에 연결
  - `--history-limit`, `--prune-history`로 실행 단위 override를 지원
  - dropped history entry 중 `.ai-republic/reports/ops/` 아래 managed bundle/archive만 안전하게 정리

- [x] `ops snapshot` history/index 상태를 dashboard와 status surface에 노출
  - dashboard가 `.ai-republic/reports/ops/latest.*`, `history.*`를 읽어 `Ops snapshots` section과 metric을 렌더링함
  - `republic status`와 `status.json|md` export가 같은 ops snapshot summary를 포함함

## 추천 다음 순서

1. live GitHub 운영 경로 guardrail과 smoke path 강화
  - [x] `doctor`가 GitHub repo access와 live publish readiness를 별도 진단함
  - [x] `republic github smoke`가 live REST readiness, issue sampling, publish preflight를 출력/export함
  - [x] REST mode에서는 `GITHUB_TOKEN`이 실제 요구사항이고 `gh auth`만으로는 충분하지 않다는 guardrail 반영
  - [x] 테스트와 문서 갱신

- [x] `sync check / repair / audit / clean`을 하나의 운영 흐름으로 더 강하게 묶기
  - `republic sync health`가 pending staged artifact, applied manifest integrity, repair preview, cleanup preview, related raw report posture를 하나의 snapshot으로 묶음
  - `--show-remediation`, `--show-mismatches`가 cleanup/sync-audit 양쪽 related-report detail block을 같은 출력 규약으로 노출함
  - `.ai-republic/reports/sync-health.json|md` export와 테스트/문서 갱신

- [x] `sync health`를 `ops snapshot` bundle과 dashboard/report flow에 포함하기
  - `republic ops snapshot`이 bundle-local `sync-health.json|md`와 root `.ai-republic/reports/sync-health.json|md`를 함께 갱신함
  - bundle manifest와 `ops status`가 `sync_health` component / related report link를 함께 기록함
  - dashboard `Reports`가 `sync-health` export를 card로 렌더링하고 `sync-audit` / cleanup report와 교차 링크함

## 추천 다음 순서

1. `ops snapshot` handoff summary를 operator-facing incident brief로 강화하기
  - bundle manifest / archive index에서 바로 읽을 수 있는 top findings, next actions, escalation summary를 추가
  - sync health, report health, latest ops history를 합친 handoff landing summary를 export에 포함
