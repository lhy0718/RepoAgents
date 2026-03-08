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

## 권장 다음 순서

1. applied sync manifest integrity 검사와 repair helper 추가
