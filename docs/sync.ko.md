# Sync Artifact

RepoAgents는 외부 시스템에 바로 반영하면 안 되는 publish 동작을 `.ai-repoagents/sync/` 아래의 tracker-agnostic staging 영역에 남깁니다.

## 왜 필요한가

다음 상황에서 sync artifact를 사용합니다.

- tracker가 의도적으로 오프라인일 때
- comment나 PR 적용 전에 사람 handoff가 필요할 때
- 외부 쓰기 제안을 결정적으로 로컬에서 검토하고 싶을 때

## 레이아웃 계약

```text
.ai-repoagents/sync/
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

- 내장 sync apply 동작은 [src/repoagents/sync_artifacts.py](../src/repoagents/sync_artifacts.py)의 `SyncActionRegistry`로 등록됩니다
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
uv run repoagents sync ls
uv run repoagents sync ls --issue 1
uv run repoagents sync ls --tracker local-file --action comment
uv run repoagents sync ls --tracker local-markdown --action pr-body
uv run repoagents sync ls --format json
```

artifact 하나 열기:

```bash
uv run repoagents sync show local-markdown/issue-1/20260308T010101000001Z-comment.md
uv run repoagents sync show 20260308T010101000001Z-comment.md
uv run repoagents sync show /absolute/path/to/file --raw
```

pending artifact 하나 적용:

```bash
uv run repoagents sync apply local-markdown/issue-1/20260308T010101000001Z-comment.md
uv run repoagents sync apply --issue 1 --tracker local-file --action comment --latest
uv run repoagents sync apply --issue 1 --tracker local-markdown --action comment --latest
uv run repoagents sync apply --issue 1 --tracker local-markdown --action pr-body --latest --bundle
uv run repoagents sync ls --scope applied --issue 1
```

applied manifest 무결성 검사와 repair:

```bash
uv run repoagents sync check --issue 1
uv run repoagents sync repair --issue 1 --dry-run
uv run repoagents sync repair --issue 1
uv run repoagents sync audit --format all
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

- `comment` artifact는 source Markdown issue frontmatter에 `repoagents` comment entry를 추가합니다
- `labels` artifact는 source Markdown issue frontmatter의 label 목록에 staged label을 merge합니다
- `branch`, `pr`, `pr-body` artifact는 `.ai-repoagents/sync-applied/` 아래의 handled handoff bundle로 archive합니다
- `repoagents sync apply --bundle`은 관련된 `branch`, `pr`, `pr-body` handoff set을 함께 해석해서 archive합니다

`local_file`의 경우:

- `comment` artifact는 source `issues.json`에 `repoagents` comment entry를 추가합니다
- `labels` artifact는 source `issues.json`의 label 목록에 staged label을 merge합니다
- `branch`, `pr`, `pr-body` artifact는 `.ai-repoagents/sync-applied/` 아래의 handled handoff bundle로 archive합니다
- `repoagents sync apply --bundle`은 관련된 `branch`, `pr`, `pr-body` handoff set을 함께 해석해서 archive합니다

모든 apply 동작은 다음 파일을 기록하거나 갱신합니다.

- `.ai-repoagents/sync-applied/<tracker>/issue-<id>/manifest.json`

manifest entry는 이제 더 풍부한 handoff linkage를 포함합니다.

- `entry_key`: source artifact path 기반의 안정적인 manifest entry id
- `archived_relative_path`: `.ai-repoagents/sync-applied/` 아래의 provider-neutral archive path
- `handoff.group_key`: bundle 또는 singleton grouping key
- `handoff.group_size`, `handoff.group_index`: 같은 handoff group 안에서의 크기와 순서
- `handoff.related_entry_keys`, `handoff.related_source_paths`: 같은 handoff set에 속한 sibling artifact 링크

`--keep-source`를 쓰지 않으면 source artifact는 `.ai-repoagents/sync/`에서 이동됩니다.

## Dashboard와 export

`repoagents dashboard`도 applied manifest를 읽어서 모든 export 형식에 `Sync handoffs`, `Sync retention`, `Reports`를 함께 렌더링합니다.

- HTML: `manifest.json`, archived artifact, normalized link target으로 바로 이동 가능한 link와 issue별 retention posture card
- JSON: `sync_handoffs[]`와 함께 prunable group 수, bytes, integrity state, age/size 데이터를 담은 `sync_retention`
- Markdown: 운영자 handoff나 incident 메모에 바로 옮길 수 있는 요약과 retention rollup
- Reports: `.ai-repoagents/reports/` 아래에 있는 `sync-audit.*`, `cleanup-preview.*`, `cleanup-result.*` export가 있으면 dashboard에서 바로 열 수 있음

특히 `Sync audit` card에는 export된 report에서 끌어온 applied manifest integrity detail도 함께 표시합니다.

- 전체 integrity report 수
- finding이 있는 issue 수와 clean issue 수
- `missing_manifest`, `duplicate_entry_key` 같은 top finding count
- 영향받은 issue id sample

sync audit export가 cleanup preview/result를 이미 연결하고 있으면 dashboard report card끼리도 서로 교차 참조합니다.

- `Sync audit`는 관련 cleanup report card로 링크됩니다
- `Cleanup preview`, `Cleanup result`는 `Sync audit`에서 참조되고 있음을 함께 보여줍니다

`Sync audit` card는 integrity finding code를 운영자용 hint로도 번역합니다. 예를 들면:

- `missing_manifest`: `repoagents sync repair --dry-run`으로 manifest state 재구성
- `duplicate_entry_key`: `repoagents sync repair --dry-run`으로 duplicate entry canonicalize
- `orphan_archive_file`: cleanup 전에 orphan archive 검토 및 편입

cleanup report card에는 freshness metadata도 함께 표시합니다.

- dashboard render 시점과 report `generated_at`을 비교한 `fresh`, `aging`, `stale`, `future` 상태
- `3d 2h` 같은 사람이 읽기 쉬운 age
- 같은 `freshness`, `age` 필드가 dashboard JSON/Markdown export에도 포함됨

linked cleanup export가 audit snapshot과 다른 `issue_filter`로 생성된 경우, dashboard `Sync audit` card는 mismatch warning도 함께 노출합니다.

- mismatch count가 report metric에 포함됩니다
- warning 문자열이 HTML, JSON, Markdown export의 report detail에도 함께 기록됩니다

`Reports` summary metric도 이제 cleanup preview/result export의 freshness를 집계해서 보여줍니다.

- HTML dashboard에 현재 `fresh`, `aging`, `stale` count를 담은 `Cleanup freshness` metric이 추가됩니다
- 같은 집계가 dashboard JSON/Markdown snapshot에도 포함됩니다

cleanup export뿐 아니라 전체 report 집합에 대한 freshness aggregate도 함께 계산합니다.

- HTML `Reports` metric row에 전체 export를 대상으로 한 `Report freshness` card가 추가됩니다
- 같은 전체 report freshness aggregate가 dashboard JSON/Markdown snapshot에도 포함됩니다

aging report는 별도 counter로도 분리되어 표시됩니다.

- HTML dashboard에 `Aging reports` 카드가 추가됩니다
- 같은 aging report count가 dashboard JSON/Markdown snapshot에도 포함됩니다

future-dated report도 별도 counter로 분리되어 표시됩니다.

- HTML dashboard에 `Future reports` 카드가 추가됩니다
- 같은 future report count가 dashboard JSON/Markdown snapshot에도 포함됩니다

freshness를 계산할 수 없는 report는 운영 경고로 따로 표시됩니다.

- count가 0이 아닐 때 HTML dashboard에 `Unknown freshness reports` 카드가 조건부로 표시됩니다
- 같은 unknown report count가 dashboard JSON/Markdown snapshot에도 포함됩니다

cleanup 전용 aging report도 별도 counter로 분리되어 표시됩니다.

- cleanup export가 있을 때 HTML dashboard에 `Cleanup aging reports` 카드가 추가됩니다
- 같은 cleanup aging report count가 dashboard JSON/Markdown snapshot에도 포함됩니다

cleanup 전용 future report도 별도 counter로 분리되어 표시됩니다.

- cleanup export가 있을 때 HTML dashboard에 `Cleanup future reports` 카드가 추가됩니다
- 같은 cleanup future report count가 dashboard JSON/Markdown snapshot에도 포함됩니다

freshness를 계산할 수 없는 cleanup report는 별도 경고로 표시됩니다.

- count가 0이 아닐 때 HTML dashboard에 `Cleanup unknown freshness reports` 카드가 조건부로 표시됩니다
- 같은 cleanup unknown report count가 dashboard JSON/Markdown snapshot에도 포함됩니다

전체 `Report freshness`와 cleanup 전용 `Cleanup freshness` aggregate에는 severity도 함께 붙습니다.

- freshness metadata 누락이나 stale report가 있으면 `issues`
- aging 또는 future report만 있으면 `attention`
- freshness가 현재 상태이거나 report가 아직 없으면 `clean`

stale cleanup export는 별도 summary card로도 분리되어 표시됩니다.

- HTML `Reports` metric row에 `Stale cleanup reports` 카드가 추가됩니다
- 같은 stale cleanup count가 dashboard JSON/Markdown snapshot에도 포함됩니다

dashboard hero banner도 최종 severity, title, reason을 그대로 반영해서, operator가 상세 `Reports` card를 읽기 전에 상단에서 report health posture를 바로 확인할 수 있습니다. 이 dashboard 전용 severity에는 raw export policy drift도 함께 반영되어, freshness count 자체는 깨끗해도 embedded policy mismatch가 있으면 hero가 `attention`으로 올라갈 수 있습니다.

`repoagents doctor`도 이제 실제 `dashboard.report_freshness_policy` threshold를 함께 보여주고, stale/unknown report가 오래 `issues`로 올라가지 않도록 너무 느슨하게 잡혀 있으면 경고를 출력하며, raw `sync-audit.json` / `cleanup-*.json` export의 embedded policy summary가 현재 config와 다를 때도 따로 경고합니다. 여기에 더해 threshold posture와 embedded-policy drift를 합친 `Report policy health` 요약도 같이 출력합니다. alignment check는 이제 `sync audit` / `clean --report`와 같은 related-report detail block 형태로 drift warning과 remediation을 보여줍니다.

`repoagents doctor --format all`은 같은 operator health snapshot을 `.ai-repoagents/reports/doctor.json`과 `.ai-repoagents/reports/doctor.md`로 export해서, CI나 handoff automation이 terminal scraping 없이도 같은 진단 결과를 읽을 수 있게 합니다.

`repoagents status`도 같은 report-health snapshot을 재사용해서, 저장된 run state와 함께 현재 report freshness severity, reason, cleanup report posture, active policy summary, 그리고 합성된 `policy_health` 요약을 바로 보여줍니다. raw report export가 더 오래된 embedded policy summary를 들고 있으면 `policy_warning` 라인 뒤에 related-report detail block을 붙여서 파일별 drift summary와 remediation guidance를 같은 형태로 보여줍니다.

`repoagents status --format all`은 filter된 run selection, report-health state, policy-alignment detail, persisted run metadata를 포함한 JSON/Markdown status snapshot을 `.ai-repoagents/reports/status.json`과 `.ai-repoagents/reports/status.md`에 export합니다.

`repoagents sync audit`도 이제 CLI summary에서 linked cleanup policy drift count를 같이 출력하고, `repoagents clean --report`도 export path 옆에 linked sync-audit drift count를 함께 보여줘서 raw JSON을 열기 전에 cross-report drift를 바로 볼 수 있습니다. remediation guidance까지 바로 보고 싶다면 두 명령 모두 `--show-remediation`을 붙이면 되고, linked issue-filter mismatch warning까지 같은 자리에서 보고 싶다면 `--show-mismatches`를 추가하면 됩니다. 두 플래그를 함께 켜면 mismatch warning, policy drift warning, remediation guidance가 하나의 related-report detail block으로 묶여 출력됩니다.

dashboard export는 이제 `policy.report_freshness_policy` metadata와 렌더링된 summary string도 함께 포함해서, downstream automation이나 공유된 snapshot만으로도 현재 severity가 어떤 threshold에서 계산됐는지 바로 확인할 수 있습니다.

각 report entry도 이제 같은 policy context를 자기 detail payload와 HTML card에 직접 포함해서, operator가 특정 report card를 읽을 때 전역 metadata row로 다시 올라가지 않아도 threshold를 바로 확인할 수 있습니다.

dashboard는 이제 각 report card의 raw `policy.summary`와 현재 config를 직접 비교해서, 오래된 export가 현재 threshold와 어긋나면 `Policy drift reports`로 드러냅니다. per-report card에서도 live policy summary와 embedded policy summary, 그리고 `doctor`/`status`와 같은 remediation guidance를 함께 보여줘서, raw report를 다시 생성해야 하는지 바로 판단할 수 있습니다.

dashboard Markdown snapshot도 이제 CLI의 related-report detail block을 따라갑니다. report entry는 기존 `details=` 요약을 유지하면서도, linked mismatch warning이나 related-report policy drift가 있으면 `related_report_details` block을 추가하고, drift가 있을 때는 같은 remediation guidance도 함께 적습니다.

HTML dashboard도 이제 같은 semantics를 `Cross references` 패널에서 직접 보여줍니다. 단순한 related note list 대신 `mismatches`와 `policy drifts` 섹션으로 나눠서 보여주고, policy drift가 있으면 같은 remediation guidance도 바로 아래에 붙습니다.

dashboard JSON export에도 이제 각 report entry에 `related_report_detail_summary` 문자열이 들어갑니다. 같은 block semantics를 평문으로 담아서, downstream tool이 구조화 배열을 다시 조립하지 않아도 warning/remediation 묶음을 바로 보여줄 수 있습니다.

이제 raw `sync-audit.json` / `cleanup-*.json` export 자체에도 같은 remediation guidance가 직접 들어갑니다.

- 관련 report의 `policy_alignment` block에 `remediation`이 포함됩니다
- related report drift summary entry에도 `remediation`이 포함됩니다
- raw export의 `related_reports` block에도 같은 mismatch / policy drift / remediation 묶음을 평문으로 담은 `detail_summary` 필드가 추가됩니다
- Markdown export에도 `policy_remediation` / `remediation` 줄이 들어가서 JSON을 열지 않아도 바로 대응할 수 있습니다

dashboard의 `Cross references` panel도 이제 related report의 policy drift note를 함께 보여줍니다. linked cleanup export나 sync audit export가 더 오래된 embedded policy로 렌더링됐으면, raw report JSON만 열지 않아도 card 안에서 바로 mismatch를 볼 수 있습니다.

유용한 명령:

```bash
uv run repoagents dashboard
uv run repoagents dashboard --format all
uv run repoagents clean --sync-applied --dry-run
uv run repoagents clean --sync-applied --dry-run --report --report-format all
```

원래 staged 파일이 이미 `.ai-repoagents/sync/`에서 이동된 경우에도 dashboard는 `self`, `metadata_artifact` 같은 normalized link를 applied archive 기준으로 다시 연결합니다.

`Sync retention` snapshot은 `cleanup.sync_applied_keep_groups_per_issue`를 기준으로 각 applied issue archive를 다음처럼 분류합니다.

- `stable`: 무결성 finding이 없고 현재 keep limit 아래에서 지울 group이 없음
- `prunable`: 무결성은 깨끗하지만 오래된 handoff group이 하나 이상 정리 대상임
- `repair-needed`: manifest integrity finding이 있어서 `sync repair` 또는 수동 점검 후에 retention을 진행해야 함

각 retention entry는 다음을 함께 보여줍니다.

- 전체/보존/정리 대상 handoff group 수
- kept/prunable bytes
- newest group age, oldest group age, oldest prunable group age
- `branch,pr` 또는 `comment` 같은 grouped action sample

`repoagents clean --sync-applied`는 manifest-aware하게 동작합니다.

- retention 계산 단위는 개별 entry가 아니라 `handoff.group_key`입니다
- `cleanup.sync_applied_keep_groups_per_issue`를 넘는 오래된 group은 함께 정리됩니다
- orphan archive 파일과 dangling manifest entry는 보수적으로 제거됩니다

`--report`를 같이 주면 cleanup도 `.ai-repoagents/reports/cleanup-preview.json|md` 또는 `.ai-repoagents/reports/cleanup-result.json|md`를 export합니다.

- JSON: action list, affected issue, manifest replacement count
- Markdown: 운영자용 cleanup 요약

`repoagents sync check`와 `repoagents sync repair`는 retention이 아니라 무결성에 집중합니다.

- `sync check`는 깨진 manifest, duplicate `entry_key`, dangling archive reference, handoff linkage mismatch, orphan archive file을 보고합니다
- `sync repair`는 살아 있는 entry를 canonicalize하고, 빠진 metadata를 복구하고, handoff linkage를 다시 계산하고, orphan archive를 `manifest.json`에 편입합니다

`repoagents sync audit`는 `.ai-repoagents/reports/` 아래에 통합 report를 export합니다.

- JSON: pending staged inventory, applied manifest integrity finding, retention summary를 한 payload에 담음
- Markdown: handoff나 async review에 바로 붙일 수 있는 운영자 요약
- Cross-links: matching `cleanup-preview.*`, `cleanup-result.*` export가 있으면 sync audit snapshot에서 함께 요약하고 연결함
- Mismatch warnings: 다른 `issue_filter`로 생성된 cleanup export는 별도 warning으로 보고해서 정상 매치처럼 보이지 않게 함
- Policy metadata: raw sync audit / cleanup report는 이제 active `report_freshness_policy` threshold를 JSON/Markdown output 안에 직접 포함함
- Cross-linked policy drift: raw sync audit entry는 linked cleanup export의 `policy_alignment`를 담고, raw cleanup report도 같은 contract로 최신 sync audit export를 역참조함
- 종료 코드: applied manifest integrity issue가 있으면 `1`, 아니면 `0`
