# Release Checklist

이 문서는 RepoRepublic 공개 릴리스를 준비하는 maintainer용 체크리스트입니다.

## 한 번에 돌리는 preflight

태그를 자르기 직전 한 번에 체크리스트를 실행하고 필요한 artifact까지 남기고 싶다면 아래 경로를 기본으로 사용합니다.

```bash
uv run republic release check --format all
bash scripts/release_preflight.sh
```

기본 `republic release check`는 다음을 한 번에 실행합니다.

- release preview target 추론
- release announcement copy pack 생성
- `uv run pytest -q`
- `uv build`
- temporary wheel install 기준 `republic --help` smoke
- 오픈소스 governance/CI 파일 존재 여부 점검

생성되는 파일:

- `.ai-republic/reports/release-checklist.json`
- `.ai-republic/reports/release-checklist.md`
- `.ai-republic/reports/release-preview.json`
- `.ai-republic/reports/release-announce.json`
- `.ai-republic/reports/release-assets.json`

저장소가 실제 publish-ready 상태일 때만 exit code가 `0`이고, blocking issue나 follow-up이 남아 있으면 non-zero로 끝나므로 태그 직전 마지막 로컬 gate로 사용할 수 있습니다.

## 릴리스 dry-run

태그를 자르기 전에 내장 preview를 먼저 실행합니다.

```bash
uv run republic release preview
uv run republic release preview --format all
uv run republic release announce --format all
uv run republic release check --format all
```

이 preview는 `republic init`으로 부트스트랩되지 않은 저장소에서도 동작합니다.

생성되는 파일:

- `.ai-republic/reports/release-preview.json`
- `.ai-republic/reports/release-preview.md`
- `.ai-republic/reports/release-notes-v<version>.md`
- `.ai-republic/reports/release-announce.json`
- `.ai-republic/reports/release-announce.md`
- `.ai-republic/reports/announcement-v<version>.md`
- `.ai-republic/reports/discussion-v<version>.md`
- `.ai-republic/reports/social-v<version>.md`
- `.ai-republic/reports/release-cut-v<version>.md`

preview가 점검하는 항목:

- `pyproject.toml`과 `src/reporepublic/__init__.py`의 버전 정합성
- `CHANGELOG.md`의 `Unreleased` 노트가 실제 release body로 쓸 수 있는 상태인지
- 요청하거나 추론한 target tag가 이미 changelog에 존재하는지
- 현재 branch와 working tree가 release-ready 상태인지

현재 프로젝트 버전에 이미 날짜가 있는 changelog section이 있고 `Unreleased`에 새 노트가 남아 있으면, RepoRepublic는 preview에서 다음 patch tag를 자동 추론합니다. 예를 들어 `0.1.0`이 이미 release section으로 존재하고 `Unreleased`에 새 항목이 있으면 preview target은 `v0.1.1`이 됩니다.

## Announcement copy pack

`republic release announce --format all`은 같은 inferred target tag를 재사용해서 maintainer용 copy pack을 생성합니다.

- short public announcement
- pinned discussion draft
- short social copy
- release-cut checklist
- GitHub release notes markdown

즉, 공개 직전에 여러 채널용 문안을 각각 수동으로 조합하지 않고, 한 번에 복사 가능한 메시지 세트를 얻는 용도입니다.

완전한 disposable rehearsal이 필요하면 아래를 실행하면 됩니다.

```bash
bash scripts/demo_release_rehearsal.sh
```

이 스크립트는 현재 저장소를 임시 workspace로 복사하고, preview/announcement artifact를 생성하고, local annotated rehearsal tag를 만들고, `uv build`를 실행한 뒤, tag/build evidence를 `.ai-republic/reports/release-rehearsal/` 아래에 남깁니다.

## Asset publish dry-run

external package index를 건드리지 않고 wheel/sdist와 post-tag upload command를 검증하려면 asset report를 사용합니다.

```bash
uv run republic release assets --format all
uv run republic release assets --build --smoke-install --format all
```

생성되는 파일:

- `.ai-republic/reports/release-assets.json`
- `.ai-republic/reports/release-assets.md`
- `.ai-republic/reports/release-assets-v<tag>.md`

asset report가 담는 내용:

- wheel/sdist 존재 여부
- artifact size와 sha256
- target version과의 정합성
- optional `uv build` 결과
- temporary venv 기반 wheel install smoke 결과
- `gh release upload`, `twine upload` 명령 초안

disposable end-to-end rehearsal이 필요하면 아래를 실행합니다.

```bash
bash scripts/demo_release_publish_dry_run.sh
```

이 스크립트는 복사한 workspace를 inferred preview version으로 맞추고, local annotated rehearsal tag를 만든 다음, `republic release assets --build --smoke-install --format all`을 실행하고, tag/build evidence를 `.ai-republic/reports/release-publish-dry-run/` 아래에 남깁니다.

## 릴리스를 자르기 전

1. working tree가 clean인지 확인합니다.
2. changelog가 갱신됐는지 확인합니다.
3. README, quickstart, docs index 링크가 현재 surface와 맞는지 확인합니다.
4. 주요 example이 계속 실행되는지 확인합니다.

## 로컬 검증

저장소 루트에서 실행합니다.

```bash
uv sync --dev
uv run pytest -q
uv build
```

선택 사항이지만 권장되는 install smoke:

```bash
python3.12 -m venv /tmp/reporepublic-release-smoke
/tmp/reporepublic-release-smoke/bin/pip install dist/*.whl
/tmp/reporepublic-release-smoke/bin/republic --help
```

live GitHub나 Codex surface를 건드렸다면 아래 opt-in smoke도 고려합니다.

```bash
CODEX_E2E=1 uv run pytest tests/test_codex_backend.py -k live_smoke -rs
GITHUB_E2E=1 REPOREPUBLIC_GITHUB_TEST_REPO=owner/name uv run pytest tests/test_tracker.py -k live_read_only -rs
```

write-path live GitHub check는 반드시 전용 sandbox repo에서만 실행합니다.

## 릴리스 노트에 들어가야 할 것

릴리스 노트에는 아래를 포함해야 합니다.

- headline user-visible feature
- safety 또는 policy 변경
- migration 또는 config 메모
- 여전히 남아 있는 known limitation

## 태그와 배포

1. [pyproject.toml](../pyproject.toml)의 `version`을 올립니다.
2. [CHANGELOG.md](../CHANGELOG.md)의 `Unreleased`를 날짜가 있는 버전 섹션으로 내립니다.
3. release prep commit을 만듭니다.
4. 예를 들어 `v0.1.1` 같은 annotated tag를 만듭니다.
5. `main`과 tag를 push합니다.
6. changelog 기반으로 GitHub release를 생성합니다.
7. PyPI에 배포할 경우 tagged commit의 CI가 green인 것을 확인한 뒤 publish합니다.

preview는 바로 복사할 수 있는 GitHub release body 파일도 생성합니다. 기본 publish 명령은 다음과 같습니다.

```bash
gh release create v0.1.1 --title "RepoRepublic v0.1.1" --notes-file .ai-republic/reports/release-notes-v0.1.1.md
```

## 릴리스 후

- 릴리스 artifact로 install 후 `republic --help`를 다시 확인합니다.
- GitHub release description의 docs 링크를 확인합니다.
- 릴리스 때문에 바뀐 roadmap이나 backlog 메모를 갱신합니다.
