# 확장 포인트

한국어 문서입니다. 영문 원문은 [extensions.md](./extensions.md)에서 볼 수 있습니다.

RepoRepublic는 의도적으로 모듈식 구조를 취합니다. MVP는 움직이는 부품 수를 줄였지만, 확장 지점은 이미 명시적으로 나뉘어 있습니다.

## 백엔드 추가

`src/reporepublic/backend/base.py`의 `BackendRunner`를 구현하면 됩니다.

- `BackendInvocation`을 입력으로 받는다
- typed Pydantic model을 반환한다
- 실패 시 `BackendExecutionError`를 발생시킨다

그 다음 `src/reporepublic/backend/factory.py`에 등록합니다.

사용 예:

- 다른 Codex 실행 프로필
- 대체 로컬 모델 runner
- review 전용 staged backend

## 트래커 추가

`src/reporepublic/tracker/base.py`의 `Tracker`를 구현하면 됩니다.

- `list_open_issues`
- `get_issue`
- `post_comment`
- `create_branch`
- `open_pr`
- `set_issue_label`

그 다음 `src/reporepublic/tracker/factory.py`에 연결합니다.

현재 내장 adapter는 다음과 같습니다.

- `github`: live REST mode와 fixture replay
- `local_file`: 로컬/오프라인 실행용 JSON inbox, `.ai-republic/sync/local-file/` 아래의 optional sidecar sync staging 포함
- `local_markdown`: 로컬/오프라인 실행용 Markdown issue 디렉터리이며, 선택적으로 `.ai-republic/sync/local-markdown/` 아래에 publish 제안을 stage할 수 있음

바로 실행 가능한 예제:

- `examples/python-lib`: GitHub tracker fixture mode
- `examples/web-app`: 경량 앱 저장소용 GitHub tracker fixture mode
- `examples/local-file-inbox`: 오프라인 JSON inbox를 사용하는 `local_file` tracker
- `examples/local-file-sync`: staged local sync proposal과 `sync apply`를 보여주는 `local_file` tracker
- `examples/local-markdown-inbox`: Markdown issue 디렉터리를 사용하는 `local_markdown` tracker
- `examples/local-markdown-sync`: comment와 draft PR 제안을 로컬에 stage하는 `local_markdown` tracker
- `examples/webhook-receiver`: GitHub 스타일 POST를 `republic webhook`으로 넘기는 로컬 HTTP receiver
- `examples/webhook-signature-receiver`: shared secret 서명 검증을 통과한 payload만 `republic webhook`으로 넘기는 로컬 HTTP receiver
- `examples/live-github-ops`: `worktree`, 파일 로그, ops helper 파일을 포함한 GitHub REST 운영 청사진

event-driven 흐름을 위해 GitHub webhook payload 파서는 `src/reporepublic/orchestrator/webhooks.py`에 있습니다. 다른 provider를 추가할 때도 같은 패턴을 따르면 됩니다. 먼저 incoming event를 단일 issue id로 정규화하고, 그 다음 polling loop 대신 orchestrator의 single-issue 실행 경로를 호출하면 됩니다.

공통 sync inventory contract와 CLI는 [sync.ko.md](./sync.ko.md)를 참고하면 됩니다.

## Sync handler 확장

tracker별 sync apply 동작은 [src/reporepublic/sync_artifacts.py](../src/reporepublic/sync_artifacts.py)의 `SyncActionRegistry`로 등록됩니다.

현재 registry는 다음을 지원합니다.

- `comment`, `labels` 같은 tracker/action별 apply handler
- `branch -> pr -> pr-body` 같은 관련 handoff set을 묶는 tracker-level bundle resolver
- archive-only action을 위한 wildcard fallback handler

파싱된 `SyncArtifact`는 다음 provider-neutral 정규화 필드도 제공합니다.

- `artifact_role`
- `issue_key`
- `bundle_key`
- `refs`
- `links`

새 오프라인 tracker에 custom `sync apply` 동작이 필요할 때는 CLI를 바꾸지 않고 이 registry를 확장하면 됩니다.

## Workspace 전략 추가

`src/reporepublic/workspace/base.py`의 `WorkspaceManager`를 구현하면 됩니다.

내장 전략은 `copy`와 `worktree`입니다. 추가 전략도 같은 오케스트레이터 계약을 재사용할 수 있습니다.

- `prepare_workspace(issue, run_id) -> Path`
- 선택적으로 `cleanup_workspace(workspace_path) -> None`

## 역할 커스터마이징

각 역할은 다음 요소를 사용합니다.

- `.ai-republic/roles/` 아래 markdown charter
- `.ai-republic/prompts/` 아래 prompt template
- `src/reporepublic/models/domain.py`의 typed output model

역할 동작을 추가하거나 교체하려면:

1. 역할 템플릿 파일을 생성하거나 수정한다
2. `src/reporepublic/roles/` 아래 role class를 갱신한다
3. 출력 계약이 바뀌면 schema model을 갱신한다
4. prompt rendering과 backend parsing 테스트를 추가한다

현재 built-in role registry는 다음 역할을 지원합니다.

- `triage`
- `planner`
- `engineer`
- `qa`
- `reviewer`

`roles.enabled`가 실행 순서를 제어합니다. core 경로는 `triage -> planner -> engineer -> reviewer`를 유지해야 하고, `qa`는 `engineer`와 `reviewer` 사이에 넣을 수 있는 optional built-in role 예시입니다.

바로 실행 가능한 role-pack 예제는 [role-packs.ko.md](./role-packs.ko.md)와 [examples/qa-role-pack/README.md](../examples/qa-role-pack/README.md)를 참고하면 됩니다.

## 정책 커스터마이징

정책 검사는 `src/reporepublic/policies/guardrails.py`에 있습니다.

다음과 같은 확장은 이 위치가 적합합니다.

- 경로 기반 제한
- diff 크기 임계값
- 저장소별 escalation 규칙
- auto-merge candidate 분류

`.ai-republic/policies/` 아래 사람용 정책 문서도 이 검사 로직과 같이 유지해야 합니다.

## 생성 템플릿 확장

`republic init`은 `src/reporepublic/templates/default/` 아래 템플릿을 복사하고 렌더링합니다.

다음 요소를 추가해 스캐폴딩 시스템을 확장할 수 있습니다.

- `src/reporepublic/templates/scaffold.py`의 새 preset
- 새 prompt template
- 새 policy document
- 추가 workflow 파일

## 대시보드 확장

정적 운영 뷰는 `src/reporepublic/dashboard.py`에 있습니다.

다음과 같은 확장을 이 위치에서 처리할 수 있습니다.

- 더 풍부한 run 카드나 필터
- artifact/log로 가는 추가 링크
- 현재 HTML, JSON, Markdown 외의 추가 출력 형식

## 테스트 전략

RepoRepublic를 확장할 때는 세 단계 테스트를 유지하는 편이 좋습니다.

1. 설정과 CLI 테스트로 setup 및 운영자 흐름을 검증
2. backend/role 테스트로 structured output 계약을 검증
3. orchestrator 테스트로 retry, 상태, scheduling, duplicate prevention을 검증
