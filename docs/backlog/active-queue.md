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
