# Issue Queue

`TODO.md`를 실제 구현 이슈 단위로 쪼갠 초안입니다. GitHub 이슈로 옮길 때는 `.github/ISSUE_TEMPLATE/implementation-task.yml`을 기본 템플릿으로 사용하면 됩니다.

## 운영 방식

- 이 문서는 우선순위 순서의 backlog입니다.
- 각 항목은 한 번에 구현 가능한 크기로 유지했습니다.
- 권장 순서는 상단부터 하단입니다.
- 구현을 시작할 때는 한 이슈만 active로 두는 편이 좋습니다.

## Queue

### RR-001. Git branch 생성과 draft PR 오픈 경로 구현

- Status: done
- Priority: P0
- Area: Tracker / Orchestrator
- Problem: 현재 `create_branch`와 `open_pr`가 실제 GitHub write path로 연결되어 있지 않아 운영 경로가 닫혀 있다.
- Scope:
  - 안전한 branch naming 규칙 추가
  - workspace 결과를 기준으로 branch 생성 경로 설계
  - 설정이 허용할 때만 draft PR 초안 생성
  - dry-run에서는 항상 외부 write 차단 유지
- Acceptance criteria:
  - [ ] `allow_open_pr=true`일 때만 PR 생성 경로가 열림
  - [ ] dry-run에서는 branch/PR write가 발생하지 않음
  - [ ] 실패 시 run state와 로그에 원인이 남음
  - [ ] 관련 테스트가 추가됨

### RR-002. PR 본문 및 issue comment 표준 템플릿 추가

- Status: done
- Priority: P0
- Area: Orchestrator / Roles
- Problem: 현재 엔지니어 결과, 테스트 결과, 리뷰 요약이 외부 공유용 메시지로 정규화되어 있지 않다.
- Scope:
  - issue comment 템플릿 추가
  - PR 본문 템플릿 추가
  - `patch_summary`, changed files, test actions, review decision 통합
- Acceptance criteria:
  - [ ] comment/PR body 생성 함수가 분리됨
  - [ ] 일관된 Markdown 포맷이 사용됨
  - [ ] dry-run에서는 생성 예정 내용이 미리 보임

### RR-003. GitHub REST adapter pagination, retry, rate-limit 처리 강화

- Status: done
- Priority: P0
- Area: Tracker
- Problem: 현재 GitHub adapter는 다수 이슈, 403/429, 네트워크 흔들림에 충분히 강하지 않다.
- Scope:
  - open issues pagination 처리
  - httpx timeout/retry/backoff 정교화
  - rate-limit 관련 structured logging 추가
- Acceptance criteria:
  - [ ] 1페이지 초과 open issues를 정상 수집함
  - [ ] 403/429/5xx에 대한 재시도 정책이 존재함
  - [ ] integration/unit test가 추가됨

### RR-004. Codex live smoke test 추가

- Status: done
- Priority: P0
- Area: Backend/Codex / Tests
- Problem: 현재 Codex backend는 command builder만 검증되고 실제 `codex exec` 연동 smoke test가 없다.
- Scope:
  - opt-in 환경 변수 기반 smoke test 추가
  - 비파괴 fixture workspace에서 Codex JSON 응답 검증
- Acceptance criteria:
  - [x] 기본 test run에는 포함되지 않음
  - [x] opt-in 시 실제 Codex 경로를 검증함
  - [x] 실패 원인이 파악 가능하도록 로그가 남음

### RR-005. `git worktree` 기반 workspace 전략 추가

- Status: done
- Priority: P1
- Area: Workspace
- Problem: copy 기반 workspace는 대형 저장소에서 느리고 비용이 크다.
- Scope:
  - `workspace.strategy: worktree` 추가
  - copy/worktree factory 분기
  - 정리(cleanup) 정책 추가
- Acceptance criteria:
  - [x] 설정으로 worktree 전략 선택 가능
  - [x] 기존 copy 전략 테스트가 유지됨
  - [x] worktree 전략 테스트가 추가됨

### RR-006. dirty working tree 감지와 운영 정책 추가

- Status: done
- Priority: P1
- Area: Workspace / CLI
- Problem: 원본 저장소가 dirty 상태여도 현재는 그대로 실행되어 기준점이 모호하다.
- Scope:
  - git 상태 감지 유틸 추가
  - warning/block/allow 정책 도입
  - `doctor` 또는 `run`에서 사전 경고 출력
- Acceptance criteria:
  - [x] dirty 상태가 감지됨
  - [x] 설정에 따라 차단 또는 경고가 가능함
  - [x] 테스트가 추가됨

### RR-007. run status / retry / clean 명령 확장

- Status: done
- Priority: P1
- Area: CLI / Orchestrator
- Problem: 현재 `status` 정보가 얕고, retry나 stale cleanup 같은 운영 기능이 없다.
- Scope:
  - `status --issue`
  - `retry <issue-id>`
  - `clean` 또는 stale cleanup 명령
- Acceptance criteria:
  - [x] 특정 issue run 조회 가능
  - [x] retry pending 상태를 강제로 재실행 가능
  - [x] 오래된 workspace/artifact 정리 경로가 존재함

### RR-008. state schema versioning 도입

- Status: done
- Priority: P1
- Area: Orchestrator / Models
- Problem: `runs.json` 구조 변경 시 호환성 문제가 생길 수 있다.
- Scope:
  - 상태 파일 version 필드 도입
  - migration hook 추가
  - 이전 포맷 로딩 전략 정의
- Acceptance criteria:
  - [x] state 파일에 version이 기록됨
  - [x] 구버전 상태를 읽을 수 있음
  - [x] migration 테스트가 추가됨

### RR-009. JSONL 파일 로깅 지원

- Status: done
- Priority: P1
- Area: Logging / Orchestrator
- Problem: 장기 실행 시 stderr만으로는 관찰성과 보존성이 부족하다.
- Scope:
  - `.ai-republic/logs/` 출력 추가
  - run-id/issue-id 포함 로그 포맷 추가
- Acceptance criteria:
  - [x] 설정으로 파일 로그 활성화 가능
  - [x] run별 추적 가능한 로그 레코드가 남음

### RR-010. triage duplicate 후보 탐지 개선

- Status: done
- Priority: P1
- Area: Roles / Tracker
- Problem: duplicate 탐지가 현재 너무 약하다.
- Scope:
  - 제목/본문 유사도 계산
  - open issue subset 비교
  - confidence 포함 결과 반환
- Acceptance criteria:
  - [x] triage 결과에 근거 있는 duplicate 후보가 담김
  - [x] false positive 방지를 위한 임계값이 존재함

### RR-011. planner repo context 개선

- Status: done
- Priority: P1
- Area: Utils / Prompts / Roles
- Problem: planner가 받는 저장소 컨텍스트가 현재 너무 얕다.
- Scope:
  - 주요 디렉터리 요약
  - 테스트 구조 요약
  - 선택적 git history/최근 변경 파일 요약
- Acceptance criteria:
  - [x] planner prompt 컨텍스트 품질이 개선됨
  - [x] context 길이 제한이 유지됨

### RR-012. reviewer diff 해석 강화

- Status: done
- Priority: P1
- Area: Roles / Policies
- Problem: reviewer가 현재 정책 위반 외의 패치 리스크를 충분히 설명하지 못한다.
- Scope:
  - diff 기반 리스크 요약
  - 테스트 부족/범위 이탈 힌트 추가
  - review_notes 정교화
- Acceptance criteria:
  - [x] reviewer notes가 diff와 테스트 맥락을 반영함
  - [x] request_changes 기준이 더 명확해짐

### RR-013. role artifact debug 확장

- Status: done
- Priority: P1
- Area: Roles / Utils
- Problem: 현재는 JSON/Markdown만 남아 디버깅에 한계가 있다.
- Scope:
  - raw prompt 저장 옵션
  - raw backend output 저장 옵션
  - debug mode 토글 추가
- Acceptance criteria:
  - [x] debug mode에서 raw I/O가 남음
  - [x] 기본 모드에서는 현재 artifact 크기를 유지함

### RR-014. 민감 파일 규칙 확장

- Status: done
- Priority: P1
- Area: Policies/Safety
- Problem: 민감 파일 탐지가 파일명 수준에 머무른다.
- Scope:
  - denylist/allowlist 정책
  - infra/auth/deploy 경로 규칙 강화
- Acceptance criteria:
  - [x] 더 넓은 민감 경로를 감지함
  - [x] repo별 정책 확장이 가능함

### RR-015. 대규모 삭제/이동 감지 정교화

- Status: done
- Priority: P1
- Area: Policies/Safety
- Problem: 현재 삭제 라인 수 기준만으로는 false positive가 생길 수 있다.
- Scope:
  - rename/move 감지 고려
  - generated/vendor 예외 처리
- Acceptance criteria:
  - [x] false positive가 줄어듦
  - [x] 정책 테스트가 추가됨

### RR-016. human approval 정책 세분화

- Status: done
- Priority: P1
- Area: Policies / Config / Orchestrator
- Problem: 현재 승인 정책이 지나치게 단일 단계다.
- Scope:
  - `comment_only`, `draft_pr`, `human_approval` 단계 설계
  - 설정 스키마 확장
- Acceptance criteria:
  - [x] 승인 단계가 설정으로 제어됨
  - [x] 기본값은 여전히 보수적임

### RR-017. `republic init` 대화형 모드

- Status: done
- Priority: P2
- Area: CLI
- Problem: 현재는 플래그 중심이라 초기 진입 장벽이 있다.
- Scope:
  - preset/tracker/backend 선택 프롬프트
  - 기본값 기반 빠른 초기화
- Acceptance criteria:
  - [x] 플래그 없이 실행해도 초기화 가능
  - [x] 비대화형 플래그 경로는 유지됨

### RR-018. `republic doctor` 진단 강화

- Status: done
- Priority: P2
- Area: CLI / Diagnostics
- Problem: 현재 doctor 출력이 얕아서 운영 문제를 빠르게 진단하기 어렵다.
- Scope:
  - GitHub auth
  - network reachability
  - template drift
  - write permission 검사
- Acceptance criteria:
  - [x] 실패 원인과 해결 힌트가 더 구체화됨
  - [x] 관련 테스트가 추가됨

### RR-019. 템플릿 업그레이드/드리프트 감지

- Status: done
- Priority: P2
- Area: Templates / CLI
- Problem: 관리 파일이 오래되면 업데이트 경로가 애매하다.
- Scope:
  - `init --upgrade` 또는 drift diff 명령
  - 로컬 수정 보존 전략
- Acceptance criteria:
  - [x] 템플릿 변경점 확인 가능
  - [x] 관리 블록 업데이트가 안전함

### RR-020. examples 실행 스크립트

- Status: done
- Priority: P2
- Area: DX / Examples
- Problem: 현재 예제 실행이 문서 수동 절차에 의존한다.
- Scope:
  - 최소 2개 데모 스크립트 추가
  - mock backend 데모 자동화
- Acceptance criteria:
  - [x] 한 줄로 예제 재현 가능
  - [x] 문서와 실제 스크립트가 일치함

### RR-021. 문서 다국어 인덱스 정리

- Status: done
- Priority: P2
- Area: Docs
- Problem: 영문/국문 문서가 생겼지만 언어별 진입점이 아직 느슨하다.
- Scope:
  - 문서 인덱스 추가
  - 언어 링크 규칙 통일
- Acceptance criteria:
  - [x] README에서 언어별 문서 탐색이 쉬워짐
  - [x] 신규 문서 규칙이 명확해짐

### RR-022. live GitHub adapter integration test

- Status: done
- Priority: P2
- Area: Tracker / Tests
- Problem: fixture mode 외 live mode 검증이 없다.
- Scope:
  - opt-in live test 추가
  - 테스트 전용 repo 또는 조건부 실행 전략 정의
- Acceptance criteria:
  - [x] 토큰 있을 때만 실행 가능
  - [x] 파괴적 write 없이 검증 가능

### RR-023. failure-path 테스트 보강

- Status: done
- Priority: P2
- Area: Tests
- Problem: timeout, malformed JSON, retry exhaustion 등의 예외 경로 테스트가 약하다.
- Scope:
  - Codex timeout
  - backend malformed JSON
  - tracker 5xx
  - retry exhaustion
- Acceptance criteria:
  - [x] 주요 실패 경로가 테스트로 고정됨

### RR-024. policy evaluation 단위 테스트 추가

- Status: done
- Priority: P2
- Area: Policies / Tests
- Problem: policy engine에 대한 직접 테스트가 아직 없다.
- Scope:
  - secrets
  - CI/CD
  - auth-sensitive
  - large deletion
- Acceptance criteria:
  - [x] 정책 케이스별 테스트가 존재함

### RR-025. scaffold snapshot 테스트 추가

- Status: done
- Priority: P2
- Area: Templates / Tests
- Problem: `republic init` 생성 결과가 의도치 않게 바뀌는 것을 막을 장치가 약하다.
- Scope:
  - preset별 생성 결과 스냅샷
  - 핵심 파일 diff 검증
- Acceptance criteria:
  - [x] preset별 템플릿 변경이 테스트에서 감지됨

### RR-026. 다중 tracker adapter 준비

- Status: done
- Priority: P3
- Area: Tracker / Config
- Problem: 현재 입력 채널이 GitHub에만 묶여 있다.
- Scope:
  - tracker factory 일반화
  - adapter 등록 패턴 정리
- Acceptance criteria:
  - [x] 복수 구현체 추가가 쉬워짐

### RR-027. 역할 확장 시스템

- Status: done
- Priority: P3
- Area: Roles / Config / Orchestrator
- Problem: 현재 4-role pipeline이 사실상 고정되어 있다.
- Scope:
  - role registry 추가
  - 설정 기반 순서 정의
- Acceptance criteria:
  - [x] 추가 role을 설정으로 연결 가능

### RR-028. webhook / event-driven 실행 모드

- Status: done
- Priority: P3
- Area: Orchestrator / Tracker
- Problem: polling-only 모델은 반응성과 비용 측면에서 한계가 있다.
- Scope:
  - webhook payload 처리 경로
  - single-issue run 엔트리포인트
- Acceptance criteria:
  - [x] webhook payload로 단일 run 시작 가능

### RR-029. 최소 운영 대시보드 초안

- Status: done
- Priority: P3
- Area: Operations / UI
- Problem: 장기적으로 run 상태 관찰성이 필요하다.
- Scope:
  - run 목록
  - artifact 링크
  - 실패 사유 표시
- Acceptance criteria:
  - [x] 최소한의 관찰 UI 초안이 존재함

### RR-030. 운영 runbook 정리

- Status: done
- Priority: P3
- Area: Docs / Operations
- Problem: 기능은 늘었지만 day-2 운영 절차가 문서로 정리되어 있지 않다.
- Scope:
  - 정상 운영 루프 정리
  - 실패/재시도/webhook 대응 절차 정리
  - artifact, state, dashboard, log 위치 문서화
- Acceptance criteria:
  - [x] 영문/국문 runbook이 존재함
  - [x] docs 인덱스와 루트 README에서 접근 가능함

### RR-031. tracker adapter 예제 확장

- Status: done
- Priority: P3
- Area: Examples / Docs
- Problem: `local_file` tracker는 구현돼 있지만, GitHub fixture 예제처럼 바로 실행 가능한 데모가 부족하다.
- Scope:
  - `local_file` tracker 예제 저장소 추가
  - 전용 demo script 추가
  - 문서에서 tracker mode별 예제 링크 정리
- Acceptance criteria:
  - [x] `local_file` tracker runnable example이 존재함
  - [x] demo script와 테스트가 추가됨

### RR-032. role pack 예제 추가

- Status: done
- Priority: P3
- Area: Examples / Docs / Roles
- Problem: optional built-in role은 구현돼 있지만, 설정과 artifact 형태를 바로 재현할 runnable example이 부족하다.
- Scope:
  - QA role pack 문서 추가
  - 전용 example repo와 demo script 추가
  - QA artifact 존재를 검증하는 테스트 추가
- Acceptance criteria:
  - [x] QA role pack runnable example이 존재함
  - [x] demo script와 테스트가 추가됨

### RR-033. webhook receiver server 예제 추가

- Status: done
- Priority: P3
- Area: Examples / Integrations / Docs
- Problem: `republic webhook` 명령은 있지만, 실제 HTTP receiver 형태로 연결하는 예제가 없었다.
- Scope:
  - 로컬 webhook receiver 예제 스크립트 추가
  - 전용 example repo와 sample payload 추가
  - end-to-end demo script와 테스트 추가
- Acceptance criteria:
  - [x] 로컬 HTTP receiver runnable example이 존재함
  - [x] demo script와 테스트가 추가됨

### RR-034. dashboard filtering/search와 live refresh 추가

- Status: done
- Priority: P3
- Area: Dashboard / CLI
- Problem: 정적 HTML 대시보드는 존재하지만, run 수가 늘면 원하는 상태를 빠르게 찾기 어렵고 자동 새로고침도 없다.
- Scope:
  - client-side 검색 입력 추가
  - status filter 추가
  - timed reload 옵션 추가
- Acceptance criteria:
  - [x] 브라우저에서 run card를 검색/상태별로 필터링할 수 있음
  - [x] `republic dashboard --refresh-seconds <n>` 경로가 존재함

### RR-035. live deployment/ops examples 추가

- Status: done
- Priority: P3
- Area: Examples / Ops / Docs
- Problem: 로컬 데모는 충분하지만, 실제 GitHub REST 운영을 준비하는 청사진 예제가 부족하다.
- Scope:
  - live GitHub ops example repo 추가
  - ops helper 파일과 bootstrap script 추가
  - production-oriented config patch 경로 검증
- Acceptance criteria:
  - [x] runnable live ops blueprint가 존재함
  - [x] demo script와 테스트가 추가됨

### RR-036. live GitHub operations walkthrough 추가

- Status: done
- Priority: P3
- Area: Docs / Ops
- Problem: live GitHub ops blueprint는 존재하지만, 운영자가 실제 저장소 기준으로 따라갈 단계별 rollout walkthrough가 부족하다.
- Scope:
  - 영문/국문 live ops walkthrough 문서 추가
  - clone/init/config/doctor/dry-run/trigger/run-loop/dashboard/failure handling 순서 문서화
  - runbook, docs index, root README, example README와 링크 연결
- Acceptance criteria:
  - [x] live GitHub 운영 절차가 단계별 문서로 존재함
  - [x] docs 인덱스와 루트 README에서 접근 가능함
  - [x] 기존 runbook 및 example 청사진과 연결됨

### RR-037. additional custom role pack examples 추가

- Status: done
- Priority: P3
- Area: Examples / Docs / DX
- Problem: built-in `qa` role pack 예제는 있지만, 새 runtime role 없이 repo-local override만으로 custom maintainer pack을 만드는 runnable example이 부족하다.
- Scope:
  - docs maintainer pack example repo 추가
  - role/prompt/policy/AGENTS override를 적용하는 demo script 추가
  - role pack 문서와 루트/문서 인덱스에서 진입 가능하게 연결
- Acceptance criteria:
  - [x] repo-local custom maintainer pack runnable example이 존재함
  - [x] demo script와 테스트가 추가됨
  - [x] role pack 문서에서 built-in pack과 custom override pack 차이가 설명됨

### RR-038. webhook auth/signature verification example 추가

- Status: done
- Priority: P3
- Area: Integrations / Examples / Security
- Problem: 로컬 webhook receiver 예제는 있지만, shared secret 기반 인증/서명 검증 경로를 보여주는 runnable example이 없다.
- Scope:
  - `scripts/webhook_receiver.py`에 선택적 signature verification 추가
  - signed webhook receiver example repo와 demo script 추가
  - helper/데모 테스트와 문서 연결
- Acceptance criteria:
  - [x] `X-Hub-Signature-256` 검증 경로가 예제 코드에 존재함
  - [x] signed webhook receiver runnable example이 존재함
  - [x] demo script와 테스트가 추가됨

### RR-039. dashboard export/share formats 추가

- Status: done
- Priority: P3
- Area: Dashboard / CLI / Docs
- Problem: 현재 대시보드는 정적 HTML 위주라 운영 스냅샷을 자동화나 공유 문맥으로 넘길 수 있는 형식이 부족하다.
- Scope:
  - `republic dashboard --format` 경로 추가
  - JSON/Markdown export 추가
  - live ops helper와 문서, 테스트 갱신
- Acceptance criteria:
  - [x] HTML 외 JSON/Markdown export가 가능함
  - [x] CLI와 테스트가 새 형식을 검증함
  - [x] 운영 문서와 예제가 새 경로를 설명함

### RR-040. additional tracker vendors/examples 추가

- Status: done
- Priority: P3
- Area: Tracker / Examples / Docs
- Problem: 현재 오프라인 tracker는 `local_file`만 있어, JSON 외의 저장소 친화적인 inbox 형태 예제가 부족하다.
- Scope:
  - `local_markdown` tracker 추가
  - Markdown issue directory example repo와 demo script 추가
  - CLI, doctor, tracker tests와 문서 진입점 갱신
- Acceptance criteria:
  - [x] `local_markdown` tracker가 실제로 Markdown issue 파일을 읽음
  - [x] demo script와 테스트가 추가됨
  - [x] README, quickstart, extensions 문서에서 새 tracker가 보임

### RR-041. additional custom tracker write paths or sync adapters 추가

- Status: done
- Priority: P3
- Area: Tracker / Sync staging / Examples / Docs
- Problem: `local_markdown` tracker는 issue inbox는 읽을 수 있지만, publish 결과를 로컬 워크플로에 넘길 write-back staging 경로가 없다.
- Scope:
  - `.ai-republic/sync/local-markdown/issue-<id>/` sidecar staging 추가
  - comment, branch, label, draft PR proposal을 로컬 파일로 기록
  - demo script, tracker tests, 문서 갱신
- Acceptance criteria:
  - [x] `local_markdown` tracker가 publish 제안을 로컬 sync 디렉터리에 stage함
  - [x] runnable demo와 테스트가 추가됨
  - [x] README, quickstart, extensions 문서에서 새 sync 경로가 설명됨

### RR-042. tracker sync artifact export/apply utility 추가

- Status: done
- Priority: P3
- Area: Tracker / CLI / Sync operations
- Problem: sidecar sync artifact가 생겨도 운영자가 어떤 staged action이 있는지 보고 적용 흐름으로 넘길 표준 CLI가 없다.
- Scope:
  - `.ai-republic/sync/` inventory를 보여주는 CLI 추가 검토
  - staged artifact export 또는 apply helper 경로 설계
  - `local_file`과 `local_markdown`에서 재사용 가능한 sync contract 정의
- Acceptance criteria:
  - [x] staged sync artifact를 issue/action 단위로 나열할 수 있음
  - [x] 추후 tracker별 apply/export 구현이 붙을 공통 contract가 문서화됨
  - [x] 문서에 운영자 후속 처리 흐름이 추가됨

### RR-043. tracker-specific sync apply helpers 추가

- Status: done
- Priority: P3
- Area: Tracker / CLI / Sync operations
- Problem: sync artifact는 볼 수 있지만, tracker별 후속 적용 절차를 표준화해 주는 helper가 아직 없다.
- Scope:
  - `local_markdown` 또는 `local_file`용 apply/export helper 검토
  - staged artifact lifecycle와 archive/cleanup 규칙 정리
  - 운영 문서와 예제 확장
- Acceptance criteria:
  - [x] 최소 한 tracker에 대해 sync apply/export helper가 제공됨
  - [x] sync artifact lifecycle이 문서와 CLI에서 일관되게 보임
  - [x] 관련 예제나 데모가 새 helper를 보여줌

### RR-044. local_file tracker sync staging 추가

- Status: done
- Priority: P3
- Area: Tracker / Sync operations / Examples
- Problem: 기존 `local_file` tracker는 read-only라 JSON inbox 경로에서 sync lifecycle을 재현할 수 없었다.
- Scope:
  - `local_file`용 sidecar sync staging 또는 export helper 추가
  - `sync apply`와 inventory 경로에서 재사용 가능한 contract 정리
  - example/demo/test 보강
- Acceptance criteria:
  - [x] `local_file` tracker도 최소 한 종류의 sync artifact를 남길 수 있음
  - [x] `sync ls`/`sync apply` 흐름과 충돌하지 않음
  - [x] 관련 예제나 테스트가 추가됨

### RR-045. branch/pr-body bundle apply helper 추가

- Status: done
- Priority: P3
- Area: Sync operations / CLI / Examples
- Problem: branch, PR metadata, PR body artifact가 따로 떨어져 있어 handoff archive를 운영자가 여러 번 적용해야 했다.
- Scope:
  - `republic sync apply --bundle` 경로 추가
  - 관련 `branch`, `pr`, `pr-body` artifact를 한 묶음으로 해석하는 helper 구현
  - CLI 테스트와 demo script 보강
- Acceptance criteria:
  - [x] `--bundle`로 관련 `branch`, `pr`, `pr-body` artifact를 한 번에 처리할 수 있음
  - [x] 개별 `sync apply` 경로와 충돌하지 않음
  - [x] demo 또는 문서가 bundle helper를 보여줌

### RR-046. tracker별 sync action registry 정리

- Status: done
- Priority: P3
- Area: Sync operations / Extensions
- Problem: sync apply 로직이 tracker 이름 하드코딩 분기에 묶여 있어 새 offline tracker나 custom action을 추가하기가 거칠었다.
- Scope:
  - tracker/action별 apply handler registry 추가
  - tracker-level bundle resolver registry 추가
  - custom registry 주입 테스트 추가
- Acceptance criteria:
  - [x] built-in tracker handler가 registry를 통해 동작함
  - [x] custom tracker/action handler를 테스트에서 주입할 수 있음
  - [x] 관련 문서가 extension seam을 설명함

### RR-047. sync artifact normalized schema 정리

- Status: done
- Priority: P3
- Area: Sync operations / Schema / Docs
- Problem: sync artifact metadata가 tracker별 필드명에 묶여 있어 downstream tooling이 `branch_name`, `metadata_path` 같은 구현 세부를 직접 알아야 했다.
- Scope:
  - provider-neutral normalized metadata block 추가
  - CLI와 manifest에 normalized schema 노출
  - 문서와 테스트 보강
- Acceptance criteria:
  - [x] `SyncArtifact`가 provider-neutral normalized field를 노출함
  - [x] `sync ls`/`sync show`/manifest에서 같은 schema를 확인할 수 있음
  - [x] 관련 문서가 normalized schema를 설명함

### RR-048. sync artifact manifest handoff linkage 확장

- Status: done
- Priority: P3
- Area: Sync operations / Manifest / Docs
- Problem: manifest가 artifact별 apply 결과는 담고 있었지만, 어떤 artifact들이 같은 handoff 묶음이었는지와 archive 후 링크를 한눈에 알기 어려웠다.
- Scope:
  - manifest entry에 richer handoff linkage field 추가
  - singleton apply와 bundle apply를 같은 linkage schema로 정렬
  - 테스트와 문서 보강
- Acceptance criteria:
  - [x] manifest entry가 `entry_key`, `archived_relative_path`, `handoff.group_*`, `related_*`를 포함함
  - [x] bundle apply 결과가 같은 handoff group으로 연결됨
  - [x] 문서가 새 manifest linkage를 설명함

### RR-049. dashboard/export에 normalized sync metadata 링크 연결

- Status: done
- Priority: P3
- Area: Dashboard / Sync operations / Docs
- Problem: applied sync manifest는 풍부해졌지만 운영자는 dashboard에서 handoff archive와 normalized link target을 바로 따라가기가 어려웠다.
- Scope:
  - dashboard snapshot에 applied sync manifest entry를 flatten해서 포함
  - HTML/JSON/Markdown export에 `Sync handoffs` 섹션 추가
  - manifest, archived artifact, normalized link target 연결
- Acceptance criteria:
  - [x] dashboard가 `.ai-republic/sync-applied/**/manifest.json`을 읽음
  - [x] HTML/JSON/Markdown export에 sync handoff 정보가 노출됨
  - [x] `metadata_artifact` 같은 normalized link가 archive 기준으로 다시 연결됨

### RR-050. sync artifact cleanup/retention 정책을 manifest-aware하게 정리

- Status: done
- Priority: P3
- Area: Sync operations / CLI / Config
- Problem: applied sync archive가 계속 쌓이면 운영자가 bundle 단위를 잃지 않고 오래된 handoff를 정리하기 어려웠다.
- Scope:
  - `cleanup.sync_applied_keep_groups_per_issue` 설정 추가
  - `republic clean --sync-applied` 경로 추가
  - manifest entry, archive file, orphan file을 handoff group 기준으로 함께 정리
- Acceptance criteria:
  - [x] retention이 manifest entry가 아니라 `handoff.group_key` 단위로 계산됨
  - [x] dangling manifest entry와 orphan archive 파일이 함께 정리됨
  - [x] dry-run preview와 테스트가 추가됨

### RR-051. applied sync manifest integrity 검사와 repair helper 추가

- Status: done
- Priority: P3
- Area: Sync operations / CLI / Integrity
- Problem: applied sync archive는 보관되지만, manifest drift나 orphan 파일이 생기면 운영자가 retention 전에 무결성 상태를 따로 진단하고 복구할 경로가 없었다.
- Scope:
  - `republic sync check` read-only integrity command 추가
  - `republic sync repair` canonicalize/adopt helper 추가
  - duplicate key, dangling archive, orphan file, handoff linkage mismatch 검사
- Acceptance criteria:
  - [x] `sync check`가 applied manifest integrity finding을 보고하고 비정상이면 non-zero로 종료함
  - [x] `sync repair`가 orphan archive를 manifest에 편입하고 handoff linkage를 재구성함
  - [x] CLI 테스트와 unit 테스트가 추가됨

### RR-052. sync-applied retention 결과를 dashboard에 age/size 기준으로 시각화

- Status: done
- Priority: P3
- Area: Dashboard / Sync operations / Retention
- Problem: applied sync archive retention은 `clean --sync-applied --dry-run`에서만 보였고, 운영자가 dashboard에서 어느 issue archive가 정리 대상인지와 정리 영향 크기를 빠르게 파악하기 어려웠다.
- Scope:
  - dashboard snapshot에 `sync_retention` 추가
  - HTML/JSON/Markdown export에 age/size 기반 retention 요약 추가
  - `stable`, `prunable`, `repair-needed` 분류와 prunable bytes/group count 노출
- Acceptance criteria:
  - [x] dashboard가 `cleanup.sync_applied_keep_groups_per_issue`를 반영한 retention snapshot을 계산함
  - [x] HTML/JSON/Markdown export에 prunable group, bytes, oldest prunable age가 노출됨
  - [x] 테스트와 문서가 추가됨

### RR-053. sync audit report export 추가

- Status: done
- Priority: P3
- Area: Sync operations / Reporting / CLI
- Problem: 운영자가 pending staged artifact, applied manifest integrity, retention 상태를 각각 따로 봐야 해서 incident handoff나 자동화 입력으로 쓰기 어려웠다.
- Scope:
  - `republic sync audit` command 추가
  - JSON/Markdown export 추가
  - pending inventory, integrity finding, retention summary를 하나의 report로 묶기
- Acceptance criteria:
  - [x] `.ai-republic/reports/sync-audit.json`과 `.md` export 경로가 동작함
  - [x] report가 pending inventory, integrity finding, retention summary를 포함함
  - [x] integrity issue가 있으면 command가 non-zero로 종료함

### RR-054. sync-applied cleanup 결과를 machine-readable report로 남기기

- Status: done
- Priority: P3
- Area: Cleanup / Reporting / CLI
- Problem: `clean --sync-applied --dry-run` 결과는 터미널 출력에만 남아서, review나 incident handoff용으로 보관 가능한 cleanup snapshot이 부족했다.
- Scope:
  - `clean --report` option 추가
  - cleanup preview/result JSON/Markdown export 추가
  - action list, affected issue, manifest rewrite count를 report로 남기기
- Acceptance criteria:
  - [x] `republic clean --sync-applied --dry-run --report`가 `.ai-republic/reports/cleanup-preview.json|md`를 생성함
  - [x] 실제 cleanup도 `.ai-republic/reports/cleanup-result.json|md`를 생성할 수 있음
  - [x] 테스트와 문서가 추가됨

### RR-055. sync audit / cleanup report를 dashboard에서 바로 열 수 있게 연결

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: sync audit와 cleanup report는 export되지만 운영자는 dashboard에서 해당 report의 존재 여부와 상태를 한 번에 확인하기 어려웠다.
- Scope:
  - dashboard snapshot에 available report summary 추가
  - HTML/JSON/Markdown export에 `Reports` 섹션 추가
  - `.ai-republic/reports/` 아래 sync audit/cleanup export 링크와 status/metric summary 노출
- Acceptance criteria:
  - [x] dashboard가 `.ai-republic/reports/`를 읽어 `sync-audit`, `cleanup-preview`, `cleanup-result` export를 탐지함
  - [x] HTML/JSON/Markdown export에 report label, status, summary, metrics가 노출됨
  - [x] 테스트와 문서가 추가됨

### RR-056. cleanup report를 sync audit에 cross-link

- Status: done
- Priority: P3
- Area: Sync operations / Reporting / Ops UX
- Problem: sync audit report는 pending/integrity/retention을 잘 묶지만, 직전 cleanup preview/result와 연결되지 않아 operator가 audit과 cleanup history를 따로 열어야 했다.
- Scope:
  - sync audit snapshot에 related cleanup report summary 추가
  - JSON/Markdown export에 cleanup preview/result path, status, metric summary 노출
  - CLI summary에 linked cleanup report count 노출
- Acceptance criteria:
  - [x] `republic sync audit`가 matching cleanup preview/result export를 감지함
  - [x] JSON/Markdown export에 related cleanup report summary가 포함됨
  - [x] 테스트와 문서가 추가됨

### RR-057. applied sync manifest integrity 요약을 dashboard report card에서 더 자세히 표시

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Integrity
- Problem: dashboard의 `Sync audit` report card는 status와 summary만 보여줘서, operator가 어떤 integrity finding이 얼마나 발생했는지와 어떤 issue가 영향을 받는지 다시 report 본문을 열어야 했다.
- Scope:
  - dashboard report entry에 integrity breakdown 추가
  - HTML card에 finding count, clean/issues split, affected issue sample 노출
  - JSON/Markdown export에도 같은 detail 포함
- Acceptance criteria:
  - [x] `Sync audit` report card가 integrity report 수, issues with findings, clean issues, finding count를 노출함
  - [x] dashboard JSON/Markdown export가 integrity detail을 포함함
  - [x] 테스트와 문서가 추가됨

### RR-058. sync audit linked cleanup report를 dashboard report card와 교차 참조

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: sync audit export가 cleanup report를 알고 있어도 dashboard에서는 각 report card가 서로 분리되어 보여서 operator가 card 사이를 바로 이동하기 어려웠다.
- Scope:
  - dashboard report entry에 card-level cross-reference 추가
  - `Sync audit`에서 related cleanup card로 이동 가능한 링크 추가
  - cleanup card에서 `Sync audit` 참조 관계 노출
- Acceptance criteria:
  - [x] `Sync audit` card가 linked cleanup report card로 이동 가능한 링크를 가짐
  - [x] cleanup report card가 `Sync audit` 참조를 노출함
  - [x] dashboard JSON/Markdown export와 테스트가 갱신됨

### RR-059. report card에서 integrity finding code를 action-oriented hint로 요약

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Integrity
- Problem: `Sync audit` card는 finding code와 count는 보여줘도, operator가 다음에 무엇을 해야 하는지 바로 읽기 어려웠다.
- Scope:
  - 주요 integrity finding code를 운영 힌트로 매핑
  - `Sync audit` card detail에 action-oriented hint 추가
  - dashboard JSON/Markdown export에 같은 hint 포함
- Acceptance criteria:
  - [x] `missing_manifest`, `duplicate_entry_key` 등 주요 finding code가 hint로 번역됨
  - [x] HTML/JSON/Markdown export가 동일한 hint를 노출함
  - [x] 테스트와 문서가 추가됨

### RR-060. sync audit related cleanup report에 issue filter mismatch 경고 추가

- Status: done
- Priority: P3
- Area: Sync operations / Reporting / Safety UX
- Problem: `sync audit --issue <id>`가 cleanup report를 연결할 때, 다른 `issue_filter`로 생성된 cleanup export를 조용히 제외해서 operator가 왜 연결되지 않았는지 알기 어려웠다.
- Scope:
  - related cleanup report loader에서 mismatch report 분리
  - JSON/Markdown export에 mismatch warning 섹션 추가
  - CLI summary에 mismatch count 출력
- Acceptance criteria:
  - [x] mismatch cleanup report가 warning으로 따로 노출됨
  - [x] matched report count와 mismatch count가 모두 보임
  - [x] 테스트와 문서가 추가됨

### RR-061. dashboard report card에 cleanup report freshness/age 표시 추가

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: cleanup preview/result card는 report가 오래되었는지 바로 보이지 않아, operator가 stale export를 최신 상태로 오해할 수 있었다.
- Scope:
  - cleanup report entry에 freshness/age 계산 추가
  - HTML card와 JSON/Markdown export에 freshness metadata 노출
  - stale cleanup report를 테스트 fixture로 고정
- Acceptance criteria:
  - [x] cleanup report card가 freshness 상태와 age를 노출함
  - [x] dashboard JSON/Markdown export가 freshness/age 필드를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-062. sync audit mismatch warning을 dashboard `Sync audit` card에도 반영

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Safety UX
- Problem: `sync audit` export는 cleanup report issue filter mismatch를 기록하지만, dashboard `Sync audit` card에는 그 경고가 직접 드러나지 않아 operator가 JSON/Markdown report를 다시 열어야 했다.
- Scope:
  - dashboard report detail에 cleanup mismatch warning과 count 추가
  - HTML/JSON/Markdown export에 같은 mismatch detail 노출
  - summary metric에 mismatch count fallback 연결
- Acceptance criteria:
  - [x] `Sync audit` card가 cleanup mismatch warning을 바로 보여줌
  - [x] dashboard JSON/Markdown export가 mismatch count와 warning 문자열을 포함함
  - [x] 테스트와 문서가 추가됨

### RR-063. cleanup report freshness를 dashboard summary metric으로 집계

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: cleanup preview/result card마다 freshness는 보이지만, operator가 dashboard 상단의 report summary만 보고 전체 cleanup export의 freshness 상태를 한눈에 파악하기는 어려웠다.
- Scope:
  - dashboard report snapshot에 cleanup freshness aggregate 추가
  - `Reports` summary metric에 cleanup report freshness 집계 노출
  - JSON/Markdown export에도 같은 aggregate 포함
- Acceptance criteria:
  - [x] dashboard가 cleanup report의 `fresh/aging/stale` 집계를 계산함
  - [x] HTML `Reports` summary metric에 aggregate freshness가 노출됨
  - [x] JSON/Markdown export와 테스트, 문서가 갱신됨

### RR-064. stale report 집계를 dashboard summary card로 분리

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: cleanup freshness aggregate가 있어도, operator가 stale cleanup export 수만 빠르게 읽으려면 metric 문자열을 다시 해석해야 했다.
- Scope:
  - `Reports` metric row에 stale cleanup 전용 card 추가
  - dashboard snapshot과 Markdown export에 stale cleanup count 노출
  - 기존 cleanup freshness aggregate는 유지
- Acceptance criteria:
  - [x] dashboard가 `Stale cleanup reports` summary card를 렌더링함
  - [x] JSON/Markdown export가 stale cleanup report count를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-065. report freshness를 전체 report 기준으로도 집계

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: cleanup export 기준 freshness aggregate는 있었지만, sync audit를 포함한 전체 report set의 freshness 상태는 operator가 직접 card별로 읽어야 했다.
- Scope:
  - dashboard report snapshot에 전체 report freshness aggregate 추가
  - `Reports` metric row에 `Report freshness` card 추가
  - JSON/Markdown export에도 같은 aggregate 포함
- Acceptance criteria:
  - [x] dashboard가 전체 report의 `fresh/aging/stale/future` 집계를 계산함
  - [x] HTML `Reports` metric row에 전체 report freshness aggregate가 노출됨
  - [x] JSON/Markdown export와 테스트, 문서가 갱신됨

### RR-066. aging report 집계를 dashboard summary card로 분리

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: 전체 report freshness aggregate가 있어도, operator가 aging report 수만 빠르게 확인하려면 metric 문자열을 해석해야 했다.
- Scope:
  - `Reports` metric row에 `Aging reports` card 추가
  - dashboard snapshot과 Markdown export에 aging report count 노출
  - 기존 overall/cleanup freshness aggregate는 유지
- Acceptance criteria:
  - [x] dashboard가 `Aging reports` summary card를 렌더링함
  - [x] JSON/Markdown export가 aging report count를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-067. future report 집계를 dashboard summary card로 분리

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: 전체 report freshness aggregate가 있어도, operator가 future-dated report 수만 빠르게 확인하려면 metric 문자열을 해석해야 했다.
- Scope:
  - `Reports` metric row에 `Future reports` card 추가
  - dashboard snapshot과 Markdown export에 future report count 노출
  - 기존 overall/cleanup freshness aggregate는 유지
- Acceptance criteria:
  - [x] dashboard가 `Future reports` summary card를 렌더링함
  - [x] JSON/Markdown export가 future report count를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-068. unknown report freshness를 dashboard warning metric으로 분리

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: report freshness aggregate에 `unknown` 값이 포함돼도, operator가 metadata 누락이나 parse failure로 freshness를 계산하지 못한 report 수를 즉시 알아보기 어려웠다.
- Scope:
  - `Reports` metric row에 `Unknown freshness reports` warning card 추가
  - dashboard snapshot과 Markdown export에 unknown report count 노출
  - unknown count가 0일 때는 card를 숨기고 aggregate는 유지
- Acceptance criteria:
  - [x] unknown freshness report가 있을 때 dashboard가 warning card를 렌더링함
  - [x] JSON/Markdown export가 unknown report count를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-069. cleanup aging report 집계를 dashboard summary card로 분리

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: cleanup freshness aggregate가 있어도, operator가 cleanup export 중 aging 상태인 report 수만 빠르게 읽으려면 metric 문자열을 해석해야 했다.
- Scope:
  - `Reports` metric row에 `Cleanup aging reports` card 추가
  - dashboard snapshot과 Markdown export에 cleanup aging report count 노출
  - 기존 cleanup freshness aggregate와 stale cleanup card는 유지
- Acceptance criteria:
  - [x] dashboard가 `Cleanup aging reports` summary card를 렌더링함
  - [x] JSON/Markdown export가 cleanup aging report count를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-070. cleanup future report 집계를 dashboard summary card로 분리

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: cleanup freshness aggregate가 있어도, operator가 cleanup export 중 future-dated report 수만 빠르게 읽으려면 metric 문자열을 해석해야 했다.
- Scope:
  - `Reports` metric row에 `Cleanup future reports` card 추가
  - dashboard snapshot과 Markdown export에 cleanup future report count 노출
  - 기존 cleanup freshness aggregate와 cleanup aging/stale cards는 유지
- Acceptance criteria:
  - [x] dashboard가 `Cleanup future reports` summary card를 렌더링함
  - [x] JSON/Markdown export가 cleanup future report count를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-071. cleanup unknown freshness를 dashboard warning metric으로 분리

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: cleanup freshness aggregate에 `unknown` 값이 포함돼도, operator가 cleanup export 중 freshness를 계산할 수 없는 report 수를 즉시 알아보기 어려웠다.
- Scope:
  - `Reports` metric row에 `Cleanup unknown freshness reports` warning card 추가
  - dashboard snapshot과 Markdown export에 cleanup unknown report count 노출
  - cleanup unknown count가 0일 때는 card를 숨기고 aggregate는 유지
- Acceptance criteria:
  - [x] cleanup unknown freshness report가 있을 때 dashboard가 warning card를 렌더링함
  - [x] JSON/Markdown export가 cleanup unknown report count를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-072. report freshness aggregate를 alert severity와 연결

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: report freshness aggregate가 숫자만 보여줘서, operator가 지금 당장 대응이 필요한지 아니면 단순 참고 수준인지 빠르게 판단하기 어려웠다.
- Scope:
  - `Report freshness`, `Cleanup freshness` aggregate에 severity 계산 추가
  - HTML summary card tone과 설명 문구에 severity 반영
  - JSON/Markdown export에도 severity와 reason 포함
- Acceptance criteria:
  - [x] overall/cleanup freshness aggregate가 `issues`, `attention`, `clean` 중 하나의 severity를 가짐
  - [x] HTML summary card와 JSON/Markdown export에 severity metadata가 노출됨
  - [x] 테스트와 문서가 추가됨

### RR-073. report freshness aggregate에 repo policy threshold를 연결

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Config
- Problem: freshness severity가 고정 규칙이라 저장소별 운영 기준에 맞게 stale/unknown/aging/future count의 민감도를 조정할 수 없었다.
- Scope:
  - `dashboard.report_freshness_policy` config 추가
  - overall/cleanup freshness severity 계산이 repo policy threshold를 읽도록 연결
  - 기본 threshold는 현재 동작과 호환되게 유지
- Acceptance criteria:
  - [x] config로 stale/unknown/future/aging threshold를 override할 수 있음
  - [x] override가 overall/cleanup freshness severity에 반영됨
  - [x] 테스트와 문서가 추가됨

### RR-074. report freshness severity를 dashboard hero summary와 연결

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: report freshness severity가 `Reports` 섹션 안에만 있어서, operator가 dashboard에 들어오자마자 현재 report health posture를 읽기 어려웠다.
- Scope:
  - hero banner가 overall/cleanup freshness severity 중 더 높은 수준을 반영하도록 연결
  - hero summary에 severity title, reason, reporting chip 추가
  - dashboard JSON/Markdown snapshot에도 같은 hero reporting summary 노출
- Acceptance criteria:
  - [x] dashboard hero가 report freshness severity를 tone과 문구로 반영함
  - [x] JSON/Markdown snapshot이 hero reporting summary를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-075. doctor에 report freshness policy 진단을 추가

- Status: done
- Priority: P3
- Area: Doctor / Dashboard / Ops UX
- Problem: `dashboard.report_freshness_policy`가 repo별로 조정 가능해졌지만, operator가 현재 threshold가 기본값인지 완화된 값인지 `doctor`만으로는 빠르게 판단할 수 없었다.
- Scope:
  - `republic doctor`에 report freshness policy diagnostic check 추가
  - 현재 threshold를 요약하고, 지나치게 느슨한 escalation은 WARN으로 표시
  - CLI 테스트와 문서 반영
- Acceptance criteria:
  - [x] `republic doctor`가 current report freshness threshold를 출력함
  - [x] 느슨한 threshold는 WARN과 hint로 surfaced 됨
  - [x] 테스트와 문서가 추가됨

### RR-076. report freshness severity를 `republic status` export와 연결

- Status: done
- Priority: P3
- Area: Status / Dashboard / Ops UX
- Problem: report freshness severity가 dashboard에만 집중되어 있어서, operator가 `republic status`만 볼 때는 현재 report health posture를 같이 읽을 수 없었다.
- Scope:
  - `republic status`가 dashboard와 같은 report-health snapshot을 재사용하도록 연결
  - overall/cleanup freshness severity, summary, reason을 CLI status output에 노출
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] `republic status`가 report health severity/title을 함께 출력함
  - [x] overall/cleanup freshness summary와 reason이 status output에 포함됨
  - [x] 테스트와 문서가 추가됨

### RR-077. report freshness policy를 dashboard/export metadata에 명시적으로 남기기

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Metadata
- Problem: report freshness severity를 계산한 threshold는 config에만 있어서, exported dashboard snapshot만 공유하면 어떤 policy 기준으로 severity가 나왔는지 바로 확인하기 어려웠다.
- Scope:
  - dashboard snapshot에 `policy.report_freshness_policy` metadata 추가
  - HTML dashboard meta row와 Markdown snapshot에 policy summary 노출
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] dashboard JSON export가 report freshness policy metadata를 포함함
  - [x] HTML/Markdown export도 같은 policy summary를 노출함
  - [x] 테스트와 문서가 추가됨

### RR-078. report freshness policy를 report card detail에도 직접 노출하기

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Metadata
- Problem: 전역 dashboard metadata에 policy threshold가 들어가도, operator가 특정 report card를 읽는 동안에는 그 카드에 어떤 threshold context가 적용됐는지 바로 확인하기 어려웠다.
- Scope:
  - 각 report entry에 policy summary와 threshold metadata 추가
  - HTML report card와 Markdown export에 per-report policy context 노출
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] report entry JSON이 policy summary와 threshold를 포함함
  - [x] HTML/Markdown report card가 per-report policy context를 보여줌
  - [x] 테스트와 문서가 추가됨

### RR-079. status 출력에도 policy threshold summary를 함께 붙이기

- Status: done
- Priority: P3
- Area: Status / Reporting / Metadata
- Problem: `republic status`가 report health severity와 reason은 보여줘도, 그 severity가 어떤 threshold baseline 위에서 계산됐는지 한 화면에서 바로 확인할 수 없었다.
- Scope:
  - `republic status` output에 active report freshness policy summary 추가
  - status 테스트와 문서 반영
- Acceptance criteria:
  - [x] `republic status`가 policy threshold summary를 출력함
  - [x] 테스트와 문서가 추가됨

### RR-080. sync audit/cleanup raw export에도 policy metadata를 직접 심기

- Status: done
- Priority: P3
- Area: Reports / Metadata / Ops UX
- Problem: dashboard snapshot에는 policy metadata가 들어가도, raw `sync-audit.json` / `cleanup-*.json`만 따로 공유하거나 자동화에 넘길 때는 어떤 threshold로 severity를 계산했는지 다시 config를 열어야 했다.
- Scope:
  - sync audit snapshot에 policy metadata 추가
  - cleanup report snapshot에 policy metadata 추가
  - Markdown export에도 policy section 추가
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] raw sync audit / cleanup JSON export가 policy metadata를 포함함
  - [x] raw sync audit / cleanup Markdown export가 policy summary를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-081. report freshness policy mismatch를 doctor/status에서 stronger warning으로 연결하기

- Status: done
- Priority: P3
- Area: Doctor / Status / Reporting / Drift Detection
- Problem: raw `sync-audit.json` / `cleanup-*.json` export가 예전 `report_freshness_policy` threshold로 생성된 뒤 config만 바뀌면, operator는 CLI에서 현재 severity baseline과 raw report embedded policy가 엇갈린 사실을 바로 보지 못했다.
- Scope:
  - raw report export의 embedded `policy.summary`를 읽는 helper 추가
  - `republic doctor`에 embedded policy mismatch 경고 추가
  - `republic status`에 `policy_warning` block 추가
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] raw report export가 현재 config와 다른 embedded policy를 가지면 `doctor`가 WARN을 출력함
  - [x] `republic status`가 mismatch file name과 summary를 함께 출력함
  - [x] embedded policy metadata가 없는 오래된 export는 mismatch로 취급하지 않음
  - [x] 테스트와 문서가 추가됨

### RR-082. dashboard가 raw report의 embedded policy metadata drift를 감지하도록 하기

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Drift Detection
- Problem: `doctor`와 `status`에서는 raw report embedded policy mismatch를 볼 수 있어도, dashboard 자체에서는 각 report card가 현재 threshold와 embedded threshold 중 무엇을 따르는지 한눈에 보이지 않았다.
- Scope:
  - dashboard report entry에 embedded policy summary/threshold metadata 추가
  - live policy 대비 drift/match/missing alignment status 계산
  - `Policy drift reports` summary card와 JSON/Markdown count 추가
  - HTML/JSON/Markdown report card detail에 alignment 정보 노출
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] dashboard HTML이 `Policy drift reports` metric과 per-report drift note를 보여줌
  - [x] dashboard JSON/Markdown snapshot이 drift/missing/embedded count와 alignment status를 포함함
  - [x] embedded policy metadata가 없는 오래된 export는 `missing`으로 표시됨
  - [x] 테스트와 문서가 추가됨

### RR-083. raw report embedded policy mismatch를 sync audit/cleanup export metadata와 cross-link하기

- Status: done
- Priority: P3
- Area: Reports / Metadata / Cross-linking
- Problem: dashboard에서는 raw report embedded policy drift를 볼 수 있어도, raw `sync-audit.json`과 `cleanup-*.json` 자체에는 linked report의 policy drift 상태가 직접 실리지 않아 downstream automation이나 공유 시 다시 계산이 필요했다.
- Scope:
  - raw sync audit `related_reports.entries`에 linked cleanup export `policy_alignment` metadata 추가
  - raw cleanup report에 latest sync audit export cross-link 추가
  - 양쪽 report의 Markdown export에 policy drift section 추가
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] raw sync audit JSON/Markdown이 linked cleanup export의 `policy_alignment`를 포함함
  - [x] raw cleanup JSON/Markdown이 linked sync audit export와 `policy_alignment`를 포함함
  - [x] current config와 다른 embedded policy는 `drift`로 표시됨
  - [x] 테스트와 문서가 추가됨

### RR-084. dashboard drift signal을 sync audit/cleanup related report section과 연결하기

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Cross References
- Problem: raw report export에는 linked report `policy_alignment`가 들어가도, dashboard에서는 그 drift signal이 각 card의 Cross references 구간으로 이어지지 않아 operator가 raw JSON 없이 관련 report drift를 바로 읽기 어려웠다.
- Scope:
  - dashboard relation parsing이 `related_reports.entries[*].policy_alignment`를 읽도록 확장
  - sync audit / cleanup report card detail에 related report drift warning 추가
  - Cross references panel에 related report drift note 표시
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] sync audit / cleanup report card가 related report policy drift warning을 detail에 노출함
  - [x] Cross references panel에서 related report drift note를 직접 볼 수 있음
  - [x] 테스트와 문서가 추가됨

### RR-085. sync audit/cleanup related report policy drift를 CLI summary로 노출하기

- Status: done
- Priority: P3
- Area: CLI / Reporting / Ops UX
- Problem: raw report와 dashboard에는 linked report policy drift가 들어가도, CLI에서 `republic sync audit`나 `republic clean --report`를 실행한 직후에는 drift count를 바로 읽기 어려웠다.
- Scope:
  - `SyncAuditBuildResult`와 `CleanupReportBuildResult`에 related policy drift count 추가
  - `republic sync audit` CLI summary에 linked cleanup policy drift count 출력
  - `republic clean --report` CLI summary에 linked sync-audit policy drift count 출력
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] `republic sync audit`가 linked cleanup policy drift count를 출력함
  - [x] `republic clean --report`가 linked sync-audit policy drift count를 출력함
  - [x] 테스트와 문서가 추가됨

### RR-086. report policy drift를 dashboard hero/report summary severity와 연결하기

- Status: done
- Priority: P3
- Area: Dashboard / Reporting / Ops UX
- Problem: `Policy drift reports` 카드와 report detail에는 drift가 보여도, dashboard hero와 report summary metric은 freshness severity만 따라가서 drift-only 상황이 상단 요약에 반영되지 않았다.
- Scope:
  - dashboard report snapshot에 `policy_drift_severity`와 `report_summary_severity` 추가
  - dashboard hero가 drift-only attention을 별도 제목으로 보여주도록 조정
  - `Report freshness` summary metric이 dashboard 전용 summary severity를 사용하도록 연결
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] freshness count는 clean이어도 policy drift가 있으면 dashboard hero가 `attention`으로 올라감
  - [x] dashboard snapshot/Markdown이 `report_summary_severity`와 `policy_drift_severity`를 포함함
  - [x] 테스트와 문서가 추가됨

### RR-087. report policy drift를 doctor/status policy health summary와 통합하기

- Status: done
- Priority: P3
- Area: CLI / Reporting / Ops UX
- Problem: dashboard에는 drift가 summary severity로 반영돼도, `doctor`와 `status`에서는 threshold posture와 embedded-policy drift가 별도 줄로만 보여서 운영자가 CLI에서 policy health를 한 번에 판단하기 어려웠다.
- Scope:
  - `Report policy health` aggregate helper 추가
  - `republic doctor`에 threshold relaxation + embedded-policy drift를 합친 summary check 추가
  - `republic status`에 `policy_health` summary line 추가
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] `republic doctor`가 threshold posture와 embedded-policy drift를 합친 `Report policy health` check를 출력함
  - [x] `republic status`가 `policy_health` line으로 같은 summary를 출력함
  - [x] 테스트와 문서가 추가됨

### RR-088. report policy drift remediation guidance를 doctor/status/dashboard에서 공통 helper로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Ops UX / Shared Helpers
- Problem: drift를 감지하는 surface가 늘면서 `dashboard`, `doctor`, `status`가 각기 다른 remediation 문구를 쓰기 시작했고, 권장 re-export 명령도 한곳에서 관리되지 않았다.
- Scope:
  - `report_policy`에 remediation summary/detail helper 추가
  - dashboard metric/card가 같은 helper를 사용하도록 정리
  - `doctor` hint와 `status` remediation line이 같은 helper를 사용하도록 정리
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] dashboard, `doctor`, `status`가 같은 remediation guidance를 출력함
  - [x] drift guidance가 한 helper에서 관리됨
  - [x] 테스트와 문서가 추가됨

### RR-089. report policy drift remediation guidance를 raw `sync-audit`/`cleanup` export 본문에도 직접 삽입하기

- Status: done
- Priority: P3
- Area: Reporting / Raw Exports / Ops UX
- Problem: `dashboard`, `doctor`, `status`에서는 drift remediation guidance를 볼 수 있어도, raw `sync-audit` / `cleanup` export 본문만 전달받은 사람은 JSON/Markdown 안에서 바로 대응 명령을 읽기 어려웠다.
- Scope:
  - raw related report `policy_alignment` payload에 `remediation` 추가
  - raw drift summary entry에 `remediation` 추가
  - raw Markdown export에 `policy_remediation` / `remediation` 줄 추가
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] raw JSON export가 drift remediation guidance를 포함함
  - [x] raw Markdown export가 remediation guidance를 직접 출력함
  - [x] 테스트와 문서가 추가됨

### RR-090. sync audit/cleanup CLI summary에도 remediation guidance를 opt-in으로 직접 출력하기

- Status: done
- Priority: P3
- Area: CLI / Reporting / Ops UX
- Problem: raw export와 dashboard에는 remediation guidance가 들어가도, `republic sync audit`와 `republic clean --report` 실행 직후에는 count만 보이고 guidance는 파일을 열어야 확인할 수 있었다.
- Scope:
  - `republic sync audit --show-remediation` 추가
  - `republic clean --report --show-remediation` 추가
  - drift count가 있을 때만 guidance를 inline 출력
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] `republic sync audit --show-remediation`이 policy drift guidance를 출력함
- [x] `republic clean --report --show-remediation`이 policy drift guidance를 출력함
- [x] 기본 출력은 기존 verbosity를 유지함
- [x] 테스트와 문서가 추가됨

### RR-091. sync audit/cleanup CLI summary에 mismatch detail도 opt-in으로 직접 출력하기

- Status: done
- Priority: P3
- Area: CLI / Reporting / Ops UX
- Problem: `republic sync audit`와 `republic clean --report`가 mismatch count는 보여줘도, 어떤 linked report가 왜 mismatch인지 확인하려면 raw export를 다시 열어야 했다.
- Scope:
  - `republic sync audit --show-mismatches` 추가
  - `republic clean --report --show-mismatches` 추가
  - linked report mismatch warning을 build result에서 직접 노출
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] `republic sync audit --show-mismatches`가 linked cleanup mismatch warning을 출력함
- [x] `republic clean --report --show-mismatches`가 linked sync audit mismatch warning을 출력함
- [x] 기본 출력은 기존 verbosity를 유지함
- [x] 테스트와 문서가 추가됨

### RR-092. report policy drift를 sync audit/cleanup CLI summary에서 mismatch detail과 함께 한 블록으로 정리하기

- Status: done
- Priority: P3
- Area: CLI / Reporting / Ops UX
- Problem: mismatch detail과 remediation guidance를 각각 따로 출력하면 linked report 상황을 읽을 때 시선이 분산되고, drift detail 자체도 count 외에는 CLI에서 한눈에 보이지 않았다.
- Scope:
  - linked report policy drift detail을 build result까지 올리기
  - `sync audit`와 `clean --report`에 공통 related-report detail block helper 추가
  - `--show-mismatches`와 `--show-remediation`를 함께 켰을 때 mismatch/drift/remediation을 한 블록으로 출력
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] `republic sync audit`가 related cleanup mismatch/drift/remediation을 한 블록으로 출력함
- [x] `republic clean --report`가 related sync-audit mismatch/drift/remediation을 한 블록으로 출력함
- [x] 단일 플래그만 켠 경우에도 같은 block 구조에서 해당 섹션만 출력함
- [x] 테스트와 문서가 추가됨

### RR-093. related-report detail block을 `doctor`/`status` 경고 출력에도 재사용하기

- Status: done
- Priority: P3
- Area: CLI / Diagnostics / Ops UX
- Problem: `sync audit` / `clean --report`는 related-report detail block으로 drift/remediation을 잘 보여주는데, `doctor`와 `status`는 여전히 별도 hint 문자열과 ad-hoc warning list를 사용해 출력 스타일이 달랐다.
- Scope:
  - `doctor`의 `Report policy export alignment` 체크에 related-report detail block 연결
  - `status`의 `policy_warning` 출력에 같은 related-report detail block 연결
  - `policy_health`는 요약 역할만 유지하도록 중복 정리
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] `doctor`가 policy drift mismatch와 remediation을 related-report detail block으로 출력함
- [x] `status`가 같은 block 구조로 drift detail을 출력함
- [x] 요약 summary와 상세 block이 중복되지 않음
- [x] 테스트와 문서가 추가됨

### RR-094. related-report detail block을 dashboard report export Markdown 요약과도 직접 맞추기

- Status: done
- Priority: P3
- Area: Dashboard / Markdown Export / Ops UX
- Problem: CLI, `doctor`, `status`는 related-report detail block으로 mismatch/drift/remediation을 읽게 됐지만, dashboard Markdown snapshot은 여전히 `details=` key-value 요약에만 의존해서 shared export만 보면 읽기 방식이 다시 달라졌다.
- Scope:
  - dashboard Markdown report entry에 `related_report_details` block 추가
  - linked mismatch warning과 related-report policy drift warning을 같은 block semantics로 렌더링
  - drift가 있을 때 remediation guidance도 block 안에 함께 출력
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] dashboard Markdown snapshot이 `related_report_details` block을 출력함
- [x] mismatch warning과 policy drift warning이 CLI와 유사한 구조로 렌더링됨
- [x] remediation guidance가 block에 포함됨
- [x] 테스트와 문서가 추가됨

### RR-095. dashboard HTML card의 Cross references 영역도 같은 block semantics를 더 직접적으로 드러내기

- Status: done
- Priority: P3
- Area: Dashboard / HTML UX / Ops UX
- Problem: Markdown snapshot은 related-report detail block을 갖게 됐지만, HTML dashboard의 `Cross references` 영역은 여전히 drift note를 평면 리스트로만 보여줘서 mismatch/drift/remediation 의미 단위가 약했다.
- Scope:
  - HTML `Cross references` 패널에 `related report details` 섹션 추가
  - linked mismatch warning과 policy drift warning을 별도 subsection으로 렌더링
  - policy drift가 있을 때 remediation guidance를 같은 패널에 추가
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] HTML report card가 `related report details`를 표시함
- [x] `mismatches`와 `policy drifts`가 별도 semantic section으로 보임
- [x] remediation guidance가 HTML에도 직접 노출됨
- [x] 테스트와 문서가 추가됨

### RR-096. dashboard JSON export에도 related-report detail block의 presentation-oriented summary string 추가하기

- Status: done
- Priority: P3
- Area: Dashboard / JSON Export / Ops UX
- Problem: HTML/Markdown은 related-report detail block을 직접 보여주지만, JSON export는 구조화 `details`만 있어 downstream consumer가 같은 표현을 다시 조립해야 했다.
- Scope:
  - report entry JSON payload에 `related_report_detail_summary` 추가
  - mismatch/drift/remediation을 평문 block으로 조합
  - 기존 structured `details`는 유지
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] dashboard JSON entry가 `related_report_detail_summary`를 포함함
  - [x] mismatch-only와 drift+remediation 케이스가 테스트로 고정됨
  - [x] 문서와 backlog가 갱신됨

### RR-097. sync audit/cleanup raw export JSON에도 related-report detail summary string 추가하기

- Status: done
- Priority: P3
- Area: Sync Reports / JSON Export / Ops UX
- Problem: dashboard JSON에는 `related_report_detail_summary`가 생겼지만, raw `sync-audit.json` / `cleanup-*.json`은 linked mismatch/drift/remediation 묶음을 바로 표시할 평문 summary가 없어 downstream consumer가 다시 조립해야 했다.
- Scope:
  - raw `related_reports` payload에 `detail_summary` 추가
  - mismatch-only와 drift+remediation 케이스를 같은 block semantics로 평문 조합
  - 기존 structured `mismatches`, `policy_drifts`, `policy_alignment`는 유지
  - 테스트와 문서 반영
- Acceptance criteria:
  - [x] raw `sync-audit.json` / `cleanup-*.json`의 `related_reports.detail_summary`가 추가됨
  - [x] mismatch-only와 drift+remediation 케이스가 테스트로 고정됨
  - [x] 문서와 backlog가 갱신됨

### RR-098. related-report detail summary builder를 dashboard/raw export 경로 사이에서 공통 helper로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: dashboard와 raw report export가 같은 related-report detail summary 문자열을 각자 따로 조합하고 있어, 포맷 drift와 중복 유지보수 비용이 생긴다.
- Scope:
  - 공통 summary builder helper 추가
  - dashboard와 raw export가 같은 helper를 사용하도록 정리
  - 출력 포맷 회귀 테스트와 pure helper 테스트 추가
- Acceptance criteria:
  - [x] dashboard와 raw export가 같은 summary formatter를 사용함
  - [x] 기존 summary 문자열 포맷이 유지됨
  - [x] helper 단위 테스트가 추가됨

### RR-099. related-report warning extraction helper도 dashboard/raw export 경로 사이에서 공통 helper로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: dashboard와 raw report export가 관련 warning을 각자 다른 helper로 추출하고 있어, string-list 경로와 structured-entry 경로의 formatting 규칙이 중복되어 있었다.
- Scope:
  - structured warning entry와 string warning list를 모두 처리하는 공통 extractor 추가
  - dashboard와 raw export가 같은 extractor를 사용하도록 정리
  - helper 단위 테스트와 회귀 테스트 유지
- Acceptance criteria:
  - [x] dashboard와 raw export가 같은 warning extractor를 사용함
  - [x] warning 문자열 포맷이 유지됨
  - [x] helper 테스트가 추가됨

### RR-100. related-report detail block markdown/html renderer를 공통 semantic block 기반으로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: CLI, dashboard Markdown, dashboard HTML이 같은 related-report detail block을 각자 따로 렌더링하고 있어 section drift와 수정 비용이 남아 있었다.
- Scope:
  - 공통 semantic block builder를 renderer 입력으로 사용
  - CLI와 dashboard Markdown이 같은 line renderer를 사용하도록 정리
  - dashboard HTML도 같은 semantic block을 소비하도록 정리
  - helper 테스트와 회귀 테스트 유지
- Acceptance criteria:
  - [x] CLI와 dashboard Markdown이 같은 line renderer를 사용함
  - [x] dashboard HTML도 같은 block semantics를 사용함
  - [x] 출력 포맷 회귀가 없고 테스트가 추가됨

### RR-101. related-report detail block title/section label 정책을 공통 helper로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: related-report detail block의 title과 section label이 surface별로 흩어져 있어, `related report details` / `related_report_details`, `policy drifts` / `policy_drifts` 같은 표현 규칙이 코드 여러 군데에 중복돼 있었다.
- Scope:
  - `display`/`machine` 스타일 기반 title/section label helper 추가
  - CLI, dashboard Markdown, dashboard HTML이 같은 label policy를 사용하도록 정리
  - helper 테스트와 회귀 테스트 유지
- Acceptance criteria:
  - [x] title과 section label 규칙이 공통 helper로 이동함
  - [x] surface별 기존 출력 포맷이 유지됨
  - [x] helper 테스트가 추가됨

### RR-102. related-report remediation label과 section ordering 정책을 공통 helper로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: related-report detail block의 remediation label과 section 순서가 구현 내부에 암묵적으로 박혀 있어, surface 간 drift를 추적하기 어려웠다.
- Scope:
  - section ordering을 공통 상수/정책으로 노출
  - remediation label formatter 추가
  - CLI, dashboard Markdown, dashboard HTML이 같은 remediation/ordering policy를 사용하도록 정리
  - helper 테스트와 회귀 테스트 유지
- Acceptance criteria:
  - [x] remediation label과 section ordering 규칙이 공통 helper로 이동함
  - [x] surface별 기존 출력 포맷이 유지됨
  - [x] helper 테스트가 추가됨

### RR-103. related-report detail block spacing/list marker 정책을 공통 helper로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: related-report detail block의 spacing/list marker 규칙이 renderer helper 밖의 호출부에 흩어져 있어, CLI와 dashboard Markdown 사이에서 indent/marker drift가 생길 수 있었다.
- Scope:
  - line layout policy helper 추가
  - title prefix, section indent, item marker, remediation line prefix를 공통 정책으로 이동
  - CLI와 dashboard Markdown이 같은 layout helper를 사용하도록 정리
  - helper 테스트와 회귀 테스트 유지
- Acceptance criteria:
  - [x] spacing/list marker 규칙이 공통 helper로 이동함
  - [x] surface별 기존 출력 포맷이 유지됨
  - [x] helper 테스트가 추가됨

### RR-104. related-report detail block HTML subtitle/spacing 정책을 공통 helper로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: related-report detail block의 HTML subtitle margin과 remediation copy spacing이 dashboard renderer 안에 하드코딩돼 있어, Markdown/CLI와는 다르게 HTML layout policy를 추적하기 어려웠다.
- Scope:
  - HTML layout policy helper 추가
  - title/section/remediation subtitle margin과 remediation copy spacing을 공통 정책으로 이동
  - dashboard HTML이 같은 helper를 사용하도록 정리
  - helper 테스트와 회귀 테스트 유지
- Acceptance criteria:
  - [x] HTML subtitle/spacing 규칙이 공통 helper로 이동함
  - [x] dashboard HTML의 기존 출력 포맷이 유지됨
  - [x] helper 테스트가 추가됨

### RR-105. related-report detail block HTML class/tag policy를 공통 helper로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: related-report detail block의 HTML renderer가 `p/ul/li/p` 태그와 class 선택을 직접 하드코딩하고 있어, subtitle/spacing helper가 있어도 HTML 표현 policy가 renderer 안에 남아 있었다.
- Scope:
  - HTML layout policy에 subtitle/list/item/copy tag와 class 선택 추가
  - list/copy/subtitle HTML 조립 helper를 공통 policy 기반으로 정리
  - dashboard HTML renderer가 직접 태그 문자열을 박지 않도록 정리
  - helper 테스트와 회귀 테스트 유지
- Acceptance criteria:
  - [x] HTML class/tag 규칙이 공통 helper로 이동함
  - [x] dashboard HTML의 기존 출력 포맷이 유지됨
  - [x] helper 테스트가 추가됨

### RR-106. related-report detail block HTML inline-style formatter를 공통 helper로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: related-report detail block의 HTML renderer가 subtitle/copy의 `style="margin-top: ..."` 문자열을 직접 조립하고 있어, HTML policy가 늘어날수록 속성 포맷 drift가 생길 수 있었다.
- Scope:
  - inline-style attribute formatter helper 추가
  - subtitle/copy renderer가 같은 style helper를 사용하도록 정리
  - dashboard HTML의 기존 출력 포맷 유지
  - helper 테스트와 회귀 테스트 유지
- Acceptance criteria:
  - [x] HTML inline-style 조립 규칙이 공통 helper로 이동함
  - [x] dashboard HTML의 기존 출력 포맷이 유지됨
  - [x] helper 테스트가 추가됨

### RR-107. related-report detail block HTML escaping/attribute rendering helper를 공통화하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: related-report detail block의 HTML renderer가 escaping, `class`, `style` 속성 조립을 부분적으로 각 helper 안에서 직접 처리하고 있어, attribute policy drift와 escaping 중복이 남아 있었다.
- Scope:
  - HTML attribute formatter helper 추가
  - escaped text element helper 추가
  - subtitle/copy/item renderer가 같은 escaping/attribute helper를 사용하도록 정리
  - helper 테스트와 회귀 테스트 유지
- Acceptance criteria:
  - [x] HTML escaping/attribute 조립 규칙이 공통 helper로 이동함
  - [x] dashboard HTML의 기존 출력 포맷이 유지됨
  - [x] helper 테스트가 추가됨

### RR-108. related-report detail block HTML wrapper/list renderer를 더 generic helper로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Ops UX
- Problem: related-report detail block의 HTML list renderer가 여전히 `<ul>...</ul>` wrapper를 직접 조립하고 있어, generic HTML wrapper policy와 text escaping 레이어가 완전히 분리되지는 않았다.
- Scope:
  - generic HTML wrapper helper 추가
  - list renderer가 wrapper helper를 재사용하도록 정리
  - text element helper는 wrapper helper 위에서 escaping만 담당하도록 정리
  - helper 테스트와 회귀 테스트 유지
- Acceptance criteria:
  - [x] HTML wrapper/list renderer 조립 규칙이 공통 helper로 이동함
  - [x] dashboard HTML의 기존 출력 포맷이 유지됨
  - [x] helper 테스트가 추가됨

### RR-109. related-report detail block HTML helper를 private 내부 contract로 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / API Hygiene
- Problem: HTML helper들이 점점 generic해지면서 외부 util contract처럼 보이기 시작했지만, 실제 소비자는 여전히 related-report detail renderer 내부에 한정돼 있어 공개 API로 취급할 이유가 약했다.
- Scope:
  - HTML helper 이름을 underscore private helper로 정리
  - 테스트를 private internal contract 기준으로 갱신
  - public 승격 기준은 backlog 메모로 남기고 현재는 내부 구현 세부사항으로 유지
- Acceptance criteria:
  - [x] HTML helper가 private internal contract로 정리됨
  - [x] 기존 동작과 테스트 결과가 유지됨
  - [x] backlog에 public 승격 판단 기준이 반영됨

### RR-110. `report_policy.py` 내부 helper cluster를 섹션 주석으로 더 명확히 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Code Readability
- Problem: `report_policy.py`가 커지면서 public policy helper, related-report builder, private HTML helper 경계가 파일만 읽어서는 바로 드러나지 않았다.
- Scope:
  - public policy snapshot/alignment helper 섹션 명시
  - related-report builder/render policy 섹션 명시
  - shared label policy와 private HTML helper 섹션 명시
  - 동작 변경 없이 코드 가독성만 개선
- Acceptance criteria:
  - [x] 파일 내부 경계가 섹션 주석으로 드러남
  - [x] 기존 동작과 테스트 결과가 유지됨
  - [x] backlog에 다음 구조화 후보가 반영됨

### RR-111. related-report detail helper cluster를 별도 internal submodule로 분리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Module Boundaries
- Problem: `report_policy.py` 안에 policy snapshot/alignment와 related-report detail renderer가 함께 있어 역할 경계가 분명해졌어도 파일 책임이 여전히 넓었다.
- Scope:
  - related-report detail 전용 타입/renderer/helper를 internal submodule로 이동
  - `report_policy.py`는 policy snapshot/alignment만 남기기
  - dashboard/CLI/sync report 경로가 새 internal module을 직접 사용하도록 정리
  - 회귀 테스트 유지
- Acceptance criteria:
  - [x] related-report detail cluster가 internal submodule로 이동함
  - [x] `report_policy.py`가 policy-only 역할로 축소됨
  - [x] 기존 동작과 테스트 결과가 유지됨

### RR-112. internal submodule 분리 후 test/module naming을 더 명확히 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Test Hygiene
- Problem: internal submodule 분리 후에도 `tests/test_report_policy.py`가 related-detail renderer를 테스트하고 있어, 파일명과 실제 책임이 어긋나 있었다.
- Scope:
  - related-detail 테스트를 별도 파일로 분리
  - `test_report_policy.py`는 policy-only 모듈 테스트로 재구성
  - 파일명과 실제 책임이 일치하도록 정리
- Acceptance criteria:
  - [x] related-detail 테스트가 별도 파일로 이동함
  - [x] `test_report_policy.py`가 policy-only 테스트를 담음
  - [x] 기존 동작과 테스트 결과가 유지됨

### RR-113. `_related_report_detail.py` 이름을 더 domain-specific하게 정리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Naming
- Problem: internal submodule이 related-report detail cluster 전체를 담는데도 파일명이 단수형이라, block/renderer/policy 묶음이라는 성격이 이름에서 충분히 드러나지 않았다.
- Scope:
  - internal submodule 이름을 `_related_report_details.py`로 조정
  - dashboard/CLI/sync report/test import를 새 이름으로 갱신
  - 테스트 파일명도 새 모듈명에 맞춰 정리
- Acceptance criteria:
  - [x] internal module 이름이 `_related_report_details.py`로 정리됨
  - [x] 소비 경로와 테스트 import가 새 이름을 사용함
  - [x] 기존 동작과 테스트 결과가 유지됨

### RR-114. related-report internal module을 package로 분리하기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Module Boundaries
- Problem: `_related_report_details.py`가 internal submodule로 분리되긴 했지만, 모델/렌더링/HTML helper가 다시 한 파일에 모여 있어 다음 구조 정리 여지가 남아 있었다.
- Scope:
  - `_related_report_details/` package 생성
  - `models.py`, `rendering.py`, `html.py`, `__init__.py`로 책임 분리
  - 기존 import 표면은 `reporepublic._related_report_details`에서 유지
  - 회귀 테스트 유지
- Acceptance criteria:
  - [x] related-report internal module이 package 구조로 분리됨
  - [x] import 표면이 유지됨
  - [x] 기존 동작과 테스트 결과가 유지됨

### RR-115. `_related_report_details` package root re-export 표면 줄이기

- Status: done
- Priority: P3
- Area: Reporting / Refactor / Internal API Hygiene
- Problem: internal package를 package 구조로 나눈 뒤에도 `__init__.py`가 많은 symbol을 다시 re-export하고 있어, private package root가 사실상 공개 API처럼 보였다.
- Scope:
  - dashboard/CLI/sync report/test가 `rendering.py`, `models.py`, `html.py`를 직접 import하도록 정리
  - `__init__.py`는 namespace marker 수준만 유지
  - 회귀 테스트 유지
- Acceptance criteria:
  - [x] 소비자가 concrete submodule을 직접 import함
  - [x] `__init__.py`가 최소 표면만 유지함
  - [x] 기존 동작과 테스트 결과가 유지됨

### RR-116. `doctor/status` operator snapshot export 추가하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / CLI
- Problem: `doctor`와 `status`는 터미널 출력은 풍부하지만 JSON/Markdown export가 없어, 운영 handoff나 automation이 현재 상태를 재사용하려면 stdout parsing에 의존해야 했다.
- Scope:
  - `doctor --format json|markdown|all --output ...` 추가
  - `status --format json|markdown|all --output ...` 추가
  - `.ai-republic/reports/doctor.*`, `status.*` 기본 export 경로 제공
  - CLI integration test와 문서 갱신
- Acceptance criteria:
  - [x] `doctor`가 structured operator snapshot을 export함
  - [x] `status`가 structured operator snapshot을 export함
  - [x] JSON/Markdown export 경로와 테스트가 추가됨

### RR-117. `ops snapshot bundle` 작업 단위 구현하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / Handoff
- Problem: `doctor`, `status`, `dashboard`, `sync audit`는 각각 export할 수 있었지만, incident handoff나 automation 입력용으로 한 디렉터리에 묶인 운영 번들이 없어 operator가 여러 명령과 경로를 따로 조합해야 했다.
- Scope:
  - `republic ops snapshot` subcommand 추가
  - `doctor/status/dashboard/sync-audit` export를 한 bundle directory로 묶기
  - `bundle.json`, `bundle.md` manifest 추가
  - bundle summary/exit code, unit/CLI 테스트, 문서 갱신
- Acceptance criteria:
  - [x] `republic ops snapshot`이 bundle directory를 생성함
  - [x] bundle manifest가 component status와 output path를 포함함
  - [x] 전체 흐름에 대한 테스트가 추가됨

### RR-118. `ops snapshot bundle`에 cleanup preview/result 선택 포함 추가하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / Handoff
- Problem: `ops snapshot bundle`이 핵심 운영 surface는 잘 묶지만 cleanup preview/result는 따로 봐야 해서, incident handoff 시 stale local state와 prior cleanup 결과를 같은 디렉터리에서 같이 전달하기 어려웠다.
- Scope:
  - `--include-cleanup-preview`로 bundle 안에서 cleanup preview 생성
  - `--include-cleanup-result`로 기존 cleanup result 복사
  - bundle manifest에 cleanup component와 sync-audit cross-link 기록
  - unit/CLI 테스트와 문서 갱신
- Acceptance criteria:
  - [x] cleanup preview가 bundle 안에 생성될 수 있음
  - [x] 기존 cleanup result를 bundle 안으로 복사할 수 있음
  - [x] bundle manifest가 cleanup/sync cross-link를 포함함

### RR-119. `ops snapshot bundle`에 sync check/repair preview 선택 포함 추가하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / Handoff
- Problem: `ops snapshot bundle`이 cleanup surface까지는 묶지만, applied sync manifest integrity와 repair preview는 별도 명령으로만 확인할 수 있어 operator가 incident handoff 시 integrity finding과 repair plan을 같은 디렉터리에서 함께 전달하기 어려웠다.
- Scope:
  - `--include-sync-check`로 bundle 안에서 dedicated sync check report 생성
  - `--include-sync-repair-preview`로 bundle 안에서 dry-run repair preview report 생성
  - bundle manifest에 `sync-audit`, `sync-check`, `sync-repair-preview` cross-link 기록
  - unit/CLI 테스트와 문서 갱신
- Acceptance criteria:
  - [x] sync check snapshot이 bundle 안에 생성될 수 있음
  - [x] sync repair preview snapshot이 bundle 안에 생성될 수 있음
  - [x] bundle manifest가 sync integrity/repair cross-link를 포함함

### RR-120. `ops snapshot bundle` archive/tarball export 추가하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / Handoff
- Problem: `ops snapshot bundle` directory는 풍부했지만, incident handoff나 외부 업로드에 바로 전달 가능한 단일 archive가 없어 operator가 bundle directory를 별도로 압축하고 checksum을 수동으로 계산해야 했다.
- Scope:
  - `republic ops snapshot --archive` 추가
  - optional `--archive-output` 경로 지원
  - `.tar.gz` archive 생성과 sha256/size/member count 출력
  - unit/CLI 테스트와 문서 갱신
- Acceptance criteria:
  - [x] bundle directory에서 `.tar.gz` archive를 생성할 수 있음
  - [x] CLI가 archive path와 checksum을 출력함
  - [x] archive에 bundle manifest와 component exports가 포함됨

### RR-121. `ops snapshot bundle` latest pointer/history index 추가하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / Automation
- Problem: `ops snapshot` bundle과 archive를 만들 수 있어도, operator나 automation이 가장 최근 handoff를 찾으려면 timestamped directory를 직접 탐색해야 해서 최신 snapshot lookup이 불안정했다.
- Scope:
  - `.ai-republic/reports/ops/latest.json|md` pointer 추가
  - `.ai-republic/reports/ops/history.json|md` bounded history index 추가
  - latest entry에 bundle path, archive path, component statuses 기록
  - unit/CLI 테스트와 문서 갱신
- Acceptance criteria:
  - [x] `ops snapshot` 실행 시 latest pointer가 갱신됨
  - [x] history index가 최신 순으로 누적됨
  - [x] custom output dir를 써도 index는 `.ai-republic/reports/ops/` 아래에서 조회 가능함

### RR-122. `ops snapshot bundle` history retention/prune policy 연결하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / Cleanup
- Problem: latest/history index가 추가된 뒤에도 오래된 bundle/archive는 계속 누적되어, operator가 handoff를 많이 만들면 `.ai-republic/reports/ops/` 아래 managed artifact가 자동으로 줄지 않았다.
- Scope:
  - `cleanup.ops_snapshot_keep_entries`, `cleanup.ops_snapshot_prune_managed`를 `republic ops snapshot` 실행 경로에 연결
  - `--history-limit`, `--prune-history` CLI override 추가
  - dropped history entry 중 `.ai-republic/reports/ops/` 아래 managed bundle/archive만 안전하게 prune
  - unit/CLI 테스트와 문서 갱신
- Acceptance criteria:
  - [x] `ops snapshot`이 config 기본 retention limit를 사용함
  - [x] `--history-limit`으로 이번 실행의 history bound를 override할 수 있음
  - [x] `--prune-history`가 외부 custom path를 건드리지 않고 managed bundle/archive만 삭제함

### RR-123. `ops snapshot` history/index 상태를 dashboard와 status surface에 노출하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / Visibility
- Problem: `ops snapshot` latest/history index는 파일로 남지만, operator가 평소 보는 `dashboard`와 `status`에서는 그 존재와 retention posture를 바로 확인할 수 없어 handoff bundle 상태를 다시 파일로 열어야 했다.
- Scope:
  - dashboard snapshot에 `ops_snapshots` section과 count 추가
  - HTML/JSON/Markdown dashboard에 latest ops snapshot, bounded history, dropped entry count 노출
  - `republic status`와 `status.json|md` export에 ops snapshot summary 추가
  - 테스트와 문서 갱신
- Acceptance criteria:
  - [x] dashboard가 `.ai-republic/reports/ops/latest.*`, `history.*`를 읽어 `Ops snapshots` section을 렌더링함
  - [x] dashboard JSON/Markdown snapshot이 ops snapshot count와 latest entry를 포함함
  - [x] `republic status`와 `status.md`가 같은 ops snapshot summary를 표시함

## 권장 다음 순서

### RR-124. dedicated `republic ops status` surface 추가하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / Visibility
- Problem: `ops snapshot` latest/history index는 dashboard와 `status`에서 요약만 보이고, 최신 indexed bundle manifest의 component summary와 recent history preview를 보려면 operator가 다시 `bundle.json`과 `latest/history` 파일을 각각 열어야 했다.
- Scope:
  - `republic ops status` subcommand 추가
  - `.ai-republic/reports/ops/latest.*`, `history.*`, 최신 indexed `bundle.json`을 함께 읽는 snapshot builder 추가
  - text + JSON/Markdown export 추가
  - 테스트와 문서 갱신
- Acceptance criteria:
  - [x] `republic ops status`가 latest/history index posture와 latest bundle manifest summary를 함께 출력함
  - [x] `republic ops status --format all`이 `.ai-republic/reports/ops-status.json|md`를 생성함
  - [x] 최신 bundle component summary와 recent history preview가 snapshot/export에 포함됨

## 권장 다음 순서

### RR-125. `ops status`를 dashboard/report flow와 더 강하게 교차 링크하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / Handoff
- Problem: dedicated `ops status` surface는 생겼지만, dashboard `Reports`와 `ops snapshot` flow는 여전히 이를 별도 수동 export처럼 취급해서 operator가 최신 handoff posture와 related report export를 한 화면에서 자연스럽게 연결해 보기 어려웠다.
- Scope:
  - dashboard `Reports`에 `ops-status` export 추가
  - `ops snapshot` 실행 시 root `ops-status.json|md` 자동 갱신
  - `ops-status` report payload에 latest bundle 기준 related report cross-link 추가
  - 테스트와 문서 갱신
- Acceptance criteria:
  - [x] dashboard가 `ops-status.json|md`를 report card로 렌더링함
  - [x] `republic ops snapshot`이 root `ops-status` export를 자동 갱신함
  - [x] `ops-status` report card가 `sync-audit` 같은 관련 report export와 cross-link됨

### RR-126. `ops snapshot` bundle 내부에도 `ops-status` export를 포함하기

- Status: done
- Priority: P2
- Area: Ops UX / Reporting / Handoff
- Problem: root `ops-status` export와 dashboard card는 생겼지만, incident handoff용 `ops snapshot` bundle 자체에는 같은 operator summary가 없어 bundle만 전달받은 사람이 latest/history posture를 다시 root reports에서 찾아야 했다.
- Scope:
  - `republic ops snapshot`이 bundle-local `ops-status.json|md`를 생성
  - bundle manifest `components.ops_status`에 output path와 metrics 기록
  - bundle cross-link가 `ops_status`와 `sync_audit` / cleanup component 관계를 함께 반영
  - 테스트와 문서 갱신
- Acceptance criteria:
  - [x] `ops snapshot` bundle directory에 `ops-status.json|md`가 포함됨
  - [x] `bundle.json`이 `ops_status` component와 관련 cross-link를 기록함
  - [x] root `ops-status` export 자동 갱신은 계속 유지됨

## 권장 다음 순서

### RR-127. live GitHub 운영 경로 guardrail과 smoke path를 강화하기

- Status: done
- Priority: P2
- Area: GitHub / Live Ops / Safety
- Problem: live GitHub adapter는 동작했지만, `doctor`가 실제 repo access와 publish preflight를 충분히 분리해서 보여주지 못했고, operator가 `tracker.repo`, issue sampling, comment/PR write readiness를 한 번에 점검할 dedicated smoke surface도 부족했다.
- Scope:
  - `doctor`에 `GitHub repo access`, `GitHub publish readiness` 진단 추가
  - `republic github smoke` subcommand 추가
  - live REST mode에서 `GITHUB_TOKEN` requirement를 명확히 하고 `gh auth` only 상태를 warning으로 노출
  - 테스트와 문서 갱신
- Acceptance criteria:
  - [x] `doctor`가 repo access와 live publish preflight를 별도 line item으로 출력함
  - [x] `republic github smoke`가 sampled issue, repo metadata, publish readiness를 출력/export함
  - [x] `--require-write-ready`가 publish preflight warning을 non-zero exit로 바꿀 수 있음

## 권장 다음 순서

1. `sync check / repair / audit / clean`을 하나의 운영 흐름으로 더 강하게 묶기

### RR-128. `sync check / repair / audit / clean`을 하나의 운영 흐름으로 더 강하게 묶기

- Status: done
- Priority: P2
- Area: Sync / Ops UX / Reporting
- Problem: sync 운영에 필요한 surface가 `sync check`, `sync repair`, `sync audit`, `clean --sync-applied --report`로 나뉘어 있어서 operator가 한 번에 현재 posture를 보기 어렵고, 어떤 명령으로 들어가야 할지 판단하려면 여러 snapshot을 따로 열어야 했다.
- Scope:
  - `republic sync health` subcommand 추가
  - pending staged artifact, applied manifest integrity, repair preview, cleanup preview, linked raw report posture를 한 snapshot으로 묶는 builder 추가
  - text + JSON/Markdown export와 related-report mismatch/remediation 출력 추가
  - 테스트와 문서 갱신
- Acceptance criteria:
  - [x] `republic sync health --issue <id>`가 sync 운영 posture를 한 번에 요약함
  - [x] `republic sync health --format all`이 `.ai-republic/reports/sync-health.json|md`를 생성함
  - [x] `--show-remediation`, `--show-mismatches`가 cleanup/sync-audit related-report detail block을 같은 규약으로 출력함

## 권장 다음 순서

1. `sync health`를 `ops snapshot` bundle과 dashboard/report flow에 포함하기

### RR-129. `sync health`를 `ops snapshot` bundle과 dashboard/report flow에 포함하기

- Status: done
- Priority: P2
- Area: Sync / Ops UX / Handoff
- Problem: `republic sync health`는 별도 surface로 존재했지만, `ops snapshot` bundle과 dashboard/report flow는 여전히 `sync-audit` 중심이라 operator가 최신 sync posture를 handoff bundle, dashboard, `ops status` 사이에서 자연스럽게 따라가기 어려웠다.
- Scope:
  - `republic ops snapshot`이 bundle-local `sync-health.json|md`와 root `.ai-republic/reports/sync-health.json|md`를 함께 갱신
  - bundle manifest / cross-link / `ops status` related report snapshot에 `sync_health` component 반영
  - dashboard `Reports`에 `sync-health` card와 related cleanup/sync-audit cross-link 추가
  - 테스트와 문서 갱신
- Acceptance criteria:
  - [x] `ops snapshot` bundle directory에 `sync-health.json|md`가 포함됨
  - [x] `bundle.json`과 `ops-status` snapshot이 `sync_health` component / related report link를 기록함
  - [x] dashboard `Reports`가 `sync-health` export를 card로 렌더링하고 related cleanup/sync-audit card와 연결함

## 권장 다음 순서

1. `ops snapshot` handoff summary를 operator-facing incident brief로 강화하기
