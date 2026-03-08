# Sync Artifact

RepoRepublic는 외부 시스템에 바로 반영하면 안 되는 publish 동작을 `.ai-republic/sync/` 아래의 tracker-agnostic staging 영역에 남깁니다.

## 왜 필요한가

다음 상황에서 sync artifact를 사용합니다.

- tracker가 의도적으로 오프라인일 때
- comment나 PR 적용 전에 사람 handoff가 필요할 때
- 외부 쓰기 제안을 결정적으로 로컬에서 검토하고 싶을 때

## 레이아웃 계약

```text
.ai-republic/sync/
  <tracker>/
    issue-<id>/
      <timestamp>-<action>.json
      <timestamp>-<action>.md
```

현재 내장 writer:

- `local-file`
- `local-markdown`

현재 내장 apply helper:

- `local-file`
- `local-markdown`

구현 메모:

- 내장 sync apply 동작은 [src/reporepublic/sync_artifacts.py](../src/reporepublic/sync_artifacts.py)의 `SyncActionRegistry`로 등록됩니다
- tracker별 handler는 CLI 계약을 바꾸지 않고 action-level effect와 bundle resolver를 추가할 수 있습니다

계약 규칙:

- `<tracker>`는 `local-markdown` 같은 filesystem-safe 정규화 이름을 사용
- `issue-<id>`는 issue 단위로 staged action을 묶음
- 파일명은 UTC timestamp 기준이라 lexicographic sort가 곧 시간순 정렬
- JSON 파일은 machine-oriented metadata payload
- Markdown 파일은 YAML frontmatter와 본문을 가진 human-oriented proposal

정규화 스키마 필드:

- `artifact_role`: `comment-proposal`, `branch-proposal`, `pr-proposal` 같은 provider-neutral 역할
- `issue_key`: `issue:1` 같은 정규화된 issue reference
- `bundle_key`: 관련 handoff artifact를 묶는 안정적인 grouping key
- `refs`: `head`, `base` 같은 정규화된 branch/base reference
- `links`: `self`, `metadata_artifact` 같은 provider-neutral artifact link

## CLI

staged artifact 목록 보기:

```bash
uv run republic sync ls
uv run republic sync ls --issue 1
uv run republic sync ls --tracker local-file --action comment
uv run republic sync ls --tracker local-markdown --action pr-body
uv run republic sync ls --format json
```

artifact 하나 열기:

```bash
uv run republic sync show local-markdown/issue-1/20260308T010101000001Z-comment.md
uv run republic sync show 20260308T010101000001Z-comment.md
uv run republic sync show /absolute/path/to/file --raw
```

pending artifact 하나 적용:

```bash
uv run republic sync apply local-markdown/issue-1/20260308T010101000001Z-comment.md
uv run republic sync apply --issue 1 --tracker local-file --action comment --latest
uv run republic sync apply --issue 1 --tracker local-markdown --action comment --latest
uv run republic sync apply --issue 1 --tracker local-markdown --action pr-body --latest --bundle
uv run republic sync ls --scope applied --issue 1
```

## 현재 의미

`local_markdown`과 `local_file`에서 staged artifact는 대체로 다음 publish proposal에 대응합니다.

- `comment.md`: issue comment proposal
- `branch.json`: branch 생성 proposal
- `pr.json`: PR metadata proposal
- `pr-body.md`: PR body proposal
- `labels.json`: label suggestion proposal

CLI inventory의 action은 파일명에 있는 action segment를 사용합니다. 실제 tracker 동작 이름은 YAML 또는 JSON metadata 안에서 다르게 보일 수 있습니다.
파싱된 artifact는 정규화 metadata block도 함께 제공하므로, downstream tooling이 `branch_name`, `metadata_path` 같은 tracker별 필드명을 직접 알 필요가 없습니다.

## 현재 apply 동작

`local_markdown`의 경우:

- `comment` artifact는 source Markdown issue frontmatter에 `reporepublic` comment entry를 추가합니다
- `labels` artifact는 source Markdown issue frontmatter의 label 목록에 staged label을 merge합니다
- `branch`, `pr`, `pr-body` artifact는 `.ai-republic/sync-applied/` 아래의 handled handoff bundle로 archive합니다
- `republic sync apply --bundle`은 관련된 `branch`, `pr`, `pr-body` handoff set을 함께 해석해서 archive합니다

`local_file`의 경우:

- `comment` artifact는 source `issues.json`에 `reporepublic` comment entry를 추가합니다
- `labels` artifact는 source `issues.json`의 label 목록에 staged label을 merge합니다
- `branch`, `pr`, `pr-body` artifact는 `.ai-republic/sync-applied/` 아래의 handled handoff bundle로 archive합니다
- `republic sync apply --bundle`은 관련된 `branch`, `pr`, `pr-body` handoff set을 함께 해석해서 archive합니다

모든 apply 동작은 다음 파일을 기록하거나 갱신합니다.

- `.ai-republic/sync-applied/<tracker>/issue-<id>/manifest.json`

manifest entry는 이제 더 풍부한 handoff linkage를 포함합니다.

- `entry_key`: source artifact path 기반의 안정적인 manifest entry id
- `archived_relative_path`: `.ai-republic/sync-applied/` 아래의 provider-neutral archive path
- `handoff.group_key`: bundle 또는 singleton grouping key
- `handoff.group_size`, `handoff.group_index`: 같은 handoff group 안에서의 크기와 순서
- `handoff.related_entry_keys`, `handoff.related_source_paths`: 같은 handoff set에 속한 sibling artifact 링크

`--keep-source`를 쓰지 않으면 source artifact는 `.ai-republic/sync/`에서 이동됩니다.

## Dashboard와 export

`republic dashboard`도 applied manifest를 읽어서 모든 export 형식에 `Sync handoffs` 섹션을 렌더링합니다.

- HTML: `manifest.json`, archived artifact, normalized link target으로 바로 이동 가능
- JSON: `sync_handoffs[]`에 `normalized`, `normalized_links`, `handoff`, archive path가 함께 기록됨
- Markdown: 운영자 handoff나 incident 메모에 바로 옮길 수 있는 요약이 생성됨

유용한 명령:

```bash
uv run republic dashboard
uv run republic dashboard --format all
uv run republic clean --sync-applied --dry-run
```

원래 staged 파일이 이미 `.ai-republic/sync/`에서 이동된 경우에도 dashboard는 `self`, `metadata_artifact` 같은 normalized link를 applied archive 기준으로 다시 연결합니다.

`republic clean --sync-applied`는 manifest-aware하게 동작합니다.

- retention 계산 단위는 개별 entry가 아니라 `handoff.group_key`입니다
- `cleanup.sync_applied_keep_groups_per_issue`를 넘는 오래된 group은 함께 정리됩니다
- orphan archive 파일과 dangling manifest entry는 보수적으로 제거됩니다
