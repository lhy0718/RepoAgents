# Active Queue

현재 바로 이어서 진행할 작업만 남긴 active queue입니다.

- 상세 이력과 완료된 작업 기록은 [issue-queue.md](./issue-queue.md)에서 확인할 수 있습니다.
- 실제 GitHub 이슈로 옮길 때는 `.github/ISSUE_TEMPLATE/implementation-task.yml`을 기본 템플릿으로 사용하면 됩니다.

## Current

### RR-144. 첫 공개 프리뷰 post-release follow-up 체크 정리

- Status: next
- Priority: P1
- Area: Release / Ops / Follow-up
- Problem: 공개 직전 preflight와 release rehearsal surface는 준비됐지만, public preview를 실제로 낸 뒤 첫 24시간 동안 어떤 점검을 해야 하는지와 feedback loop를 어떻게 운영해야 하는지는 아직 정리되지 않았다.
- Scope:
  - release 이후 issue triage, docs link 확인, install feedback 수집 경로를 한 번 더 정리
  - public preview 다음 24시간 운영 checklist를 runnable artifact나 문서로 제공
  - release guide, runbook, README에서 post-release 운영 진입점을 연결
- Acceptance criteria:
  - [ ] post-release follow-up checklist가 문서 또는 runnable artifact로 존재함
  - [ ] maintainer가 첫 24시간 동안 확인할 install/docs/feedback 항목이 명시됨
  - [ ] README 또는 runbook에서 해당 follow-up surface로 바로 이동할 수 있음

## Productization Candidates

`RR-144` 이후 일반 사용성을 높이기 위해 승격할 후보 작업입니다.

### P0. 단일 저장소 실사용 안정화

### RR-145. foreground loop 의존 없이 안정적으로 도는 worker/service 모드 추가

- Status: candidate
- Priority: P0
- Area: Orchestrator / CLI / Ops
- Problem: 현재 `repoagents run`은 foreground polling loop 중심이라 terminal/session lifecycle에 강하게 묶이고, retry queue가 언제 다시 소비되는지 운영자가 직관적으로 알기 어렵다.
- Scope:
  - repo 단위 worker/service entrypoint와 상태 파일 설계
  - heartbeat, lease, graceful stop/restart, stale worker 감지 추가
  - `status`/`dashboard`가 현재 worker 상태와 last poll 시각을 직접 보여주도록 연결
- Acceptance criteria:
  - [x] foreground terminal이 끊겨도 repo 단위 worker lifecycle을 재개/정지할 수 있음
  - [x] stale worker 또는 idle poll 상태가 `status`/`dashboard`에서 구분되어 보임
  - [x] retry pending run이 다음 poll에 의해 다시 소비되는 경로가 문서와 UI에 명시됨

### RR-146. human approval을 실제 승인 inbox/명령으로 묶기

- Status: candidate
- Priority: P0
- Area: CLI / Dashboard / Orchestrator
- Problem: `human_approval` 정책은 존재하지만, maintainer가 “무엇을 승인/반려하는지”를 한 곳에서 읽고 결정하는 surface는 아직 분산돼 있다.
- Scope:
  - 승인 대기 중인 comment/branch/PR draft를 한 번에 보여주는 inbox 추가
  - `approve`, `reject`, `retry` 같은 명령 또는 dashboard action 설계
  - 승인/반려 이유와 결정 이력을 artifact/state/log에 남기기
- Acceptance criteria:
  - [x] maintainer가 승인 대기 항목을 하나의 surface에서 확인할 수 있음
  - [x] approve/reject 결정이 run state와 artifact에 기록됨
  - [x] 승인 전 외부 write 금지라는 기존 안전 경계가 유지됨

### RR-147. 첫 실행까지 가는 guided setup과 `doctor --fix` 경로 추가

- Status: candidate
- Priority: P0
- Area: CLI / Config / Docs
- Problem: 현재도 `init`/`doctor`는 있지만, 일반 사용자는 Codex login, GitHub auth, tracker 설정, 첫 trigger 검증까지 여러 단계를 수동으로 따라가야 한다.
- Scope:
  - `doctor --fix` 또는 setup helper로 자동 수정 가능한 항목 정리
  - Codex/GitHub auth, writable path, tracker repo, preset drift를 단계별로 안내
  - 샘플 issue 기반 first run validation flow 추가
- Acceptance criteria:
  - [ ] fresh repo가 guided setup만으로 첫 `trigger --dry-run`까지 도달할 수 있음
  - [ ] 자동 수정 가능한 doctor finding은 별도 명령으로 복구 가능함
  - [ ] runbook/README가 “첫 성공 run”까지의 경로를 더 짧게 안내함

### RR-148. publish retry, resume, cleanup를 idempotent하게 정리하기

- Status: candidate
- Priority: P0
- Area: Tracker / Orchestrator / Publication
- Problem: branch/PR publish 경로는 존재하지만, 중간 실패 뒤 재실행할 때 duplicate branch/PR 생성이나 cleanup 누락을 더 강하게 제어할 필요가 있다.
- Scope:
  - publish 단계별 external object id 저장과 resume 규칙 추가
  - duplicate PR/branch 방지와 safe cleanup helper 강화
  - publish failure를 comment/branch/PR 단계별로 분류해 surface에 반영
- Acceptance criteria:
  - [ ] 같은 issue 재실행이 duplicate publish artifact를 만들지 않음
  - [ ] partially published run을 resume 또는 cleanup 가능한 상태로 남김
  - [ ] publish 단계별 실패 원인이 `status`/`dashboard`/logs에 구분되어 보임

### P1. 작은 팀 협업과 운영 가시성 확장

### RR-149. static dashboard를 live ops UI와 event stream으로 확장하기

- Status: candidate
- Priority: P1
- Area: Dashboard / Ops / Reporting
- Problem: 현재 dashboard는 static HTML/TUI 중심이라 수동 refresh 없이 실시간 상태 변화를 공유하거나 여러 운영자가 동시에 보기 어렵다.
- Scope:
  - run/report/worker 상태를 제공하는 read-only local API 설계
  - live refresh 또는 event stream 기반 web UI 추가
  - 기존 HTML/JSON/Markdown export와 공존하는 운영 surface 설계
- Acceptance criteria:
  - [ ] run 상태 변화가 수동 재렌더 없이 UI에 반영됨
  - [ ] 기존 static export는 유지되면서 live surface가 추가됨
  - [ ] 여러 운영자가 같은 상태를 읽을 때 표현 차이가 줄어듦

### RR-150. failure, stuck run, approval-needed 알림 sink 추가

- Status: candidate
- Priority: P1
- Area: Ops / Notifications / Reporting
- Problem: 현재 운영자는 dashboard나 logs를 열어봐야 이상 상태를 발견할 수 있어, unattended 운영에 필요한 push notification이 부족하다.
- Scope:
  - Slack/webhook/email 중 최소 한 가지 notification sink 추가
  - failed, retry exhaustion, stale worker, approval-needed 이벤트 규칙 정의
  - 알림 payload에 run id, issue id, artifact/status 링크 요약 포함
- Acceptance criteria:
  - [ ] 핵심 운영 이벤트가 polling 없이 외부 채널로 전달됨
  - [ ] alert noise를 줄일 수 있는 최소 설정이 존재함
  - [ ] runbook에서 alert 발생 후 follow-up 절차를 바로 찾을 수 있음

### RR-151. GitHub 외 tracker 확장을 위한 adapter SDK와 첫 vendor adapter 추가

- Status: candidate
- Priority: P1
- Area: Tracker / Extensions
- Problem: 현재 RepoAgents는 GitHub와 local inbox 흐름에 강하게 최적화되어 있어, 일반적인 팀 도구 환경으로 확장하기 어렵다.
- Scope:
  - tracker capability contract를 더 명시적으로 나누기
  - adapter authoring guide와 test fixture pattern 정리
  - GitLab, Linear, Jira 중 최소 하나의 hosted adapter 또는 runnable example 추가
- Acceptance criteria:
  - [ ] GitHub 외 tracker 하나가 동일한 orchestrator flow를 재사용함
  - [ ] 새 tracker adapter를 추가하는 문서와 test skeleton이 존재함
  - [ ] runbook/README에서 non-GitHub 경로 진입점이 보임

### RR-152. 사용량, 실행시간, 실패율을 보여주는 운영 telemetry 추가

- Status: candidate
- Priority: P1
- Area: Reporting / Logging / Dashboard
- Problem: 현재는 run summary와 artifact는 남지만, 비용/시간/실패율 같은 운영 지표가 부족해 scale-out 시 판단 근거가 약하다.
- Scope:
  - run/role duration, retry count, failure class, backend exit profile 수집
  - dashboard/status/report export에 aggregate telemetry 추가
  - repo 단위 budget 또는 warning threshold 설계
- Acceptance criteria:
  - [ ] maintainer가 run latency와 failure trend를 surface에서 바로 볼 수 있음
  - [ ] slow/flaky repo를 구분할 수 있는 기본 지표가 존재함
  - [ ] telemetry가 로그 scraping 없이 JSON/Markdown export에도 남음

### P2. 다중 팀/다중 저장소 배포 기반

### RR-153. multi-repo worker와 중앙 queue를 위한 control plane 초안 추가

- Status: candidate
- Priority: P2
- Area: Orchestrator / Service / Ops
- Problem: 현재 구조는 repo-local state 중심이라 여러 저장소를 한 프로세스/한 화면에서 관리하는 조직 단위 운영 모델로 확장하기 어렵다.
- Scope:
  - repo registration, queue, lease, worker heartbeat를 담는 control plane 초안 설계
  - single-repo local mode와 공존 가능한 state migration 방향 정리
  - multi-repo 운영자가 볼 최소 summary surface 정의
- Acceptance criteria:
  - [ ] 여러 repo를 하나의 상위 queue/model로 표현할 수 있음
  - [ ] 기존 repo-local mode를 깨지 않는 migration 방향이 문서화됨
  - [ ] control plane 도입 전후의 책임 경계가 architecture 문서에 반영됨

### RR-154. Codex 단일 의존을 줄이는 production backend abstraction 확장

- Status: candidate
- Priority: P2
- Area: Backend / Config / Tests
- Problem: 현재 production backend가 사실상 `codex exec` 설치와 login 상태에 묶여 있어, 조직 환경마다 다른 모델 런타임을 쓰기 어렵다.
- Scope:
  - backend capability schema와 fallback 정책 정리
  - Codex 외 production-grade backend 하나 이상 추가
  - backend별 smoke test, failure taxonomy, config docs 정리
- Acceptance criteria:
  - [ ] 같은 orchestrator flow가 두 개 이상의 production backend에서 동작함
  - [ ] backend별 제한과 fallback 규칙이 설정/문서에 명시됨
  - [ ] backend 차이가 operator surface에서 이해 가능한 수준으로 노출됨

### RR-155. 조직 공통 policy bundle, audit export, ownership routing 추가

- Status: candidate
- Priority: P2
- Area: Policies / Audit / Workflow
- Problem: 여러 팀이 함께 쓰려면 repo-local prompt/policy만으로는 부족하고, 공통 정책 배포와 승인 라우팅, audit trail이 필요하다.
- Scope:
  - org-level policy bundle과 repo override 합성 규칙 설계
  - approval/rejection/publish 이력을 audit export로 남기기
  - CODEOWNERS 또는 ownership map 기반 reviewer/approver routing 연결
- Acceptance criteria:
  - [ ] 공통 정책과 repo override를 함께 적용하는 규칙이 존재함
  - [ ] 승인 및 publish 이력이 machine-readable export로 남음
  - [ ] ownership 기반 approval routing 경로가 최소 한 가지 surface에서 동작함
