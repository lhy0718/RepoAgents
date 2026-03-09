# 문서 인덱스

RepoRepublic는 다국어 문서를 같은 위치에 두고, 아래 규칙으로 관리합니다.

- 영어 원문은 `name.md`
- 한국어 번역은 `name.ko.md`
- 새 문서도 같은 디렉터리에서 같은 규칙을 유지

## 루트 가이드

- 영문 개요: [README.md](../README.md)
- 국문 개요: [README.ko.md](../README.ko.md)
- 영문 빠른 시작: [QUICKSTART.md](../QUICKSTART.md)
- 국문 빠른 시작: [QUICKSTART.ko.md](../QUICKSTART.ko.md)

## 아키텍처

- 영문: [architecture.md](./architecture.md)
- 국문: [architecture.ko.md](./architecture.ko.md)

## 확장 포인트

- 영문: [extensions.md](./extensions.md)
- 국문: [extensions.ko.md](./extensions.ko.md)
- sync artifact: [sync.md](./sync.md), [sync.ko.md](./sync.ko.md)
- role pack 예제: [role-packs.md](./role-packs.md), [role-packs.ko.md](./role-packs.ko.md)

## 운영 문서

- 영문: [runbook.md](./runbook.md)
- 국문: [runbook.ko.md](./runbook.ko.md)
- Live GitHub 운영 walkthrough: [live-github-ops.md](./live-github-ops.md), [live-github-ops.ko.md](./live-github-ops.ko.md)
- Sandbox publish rollout: [live-github-sandbox-rollout.md](./live-github-sandbox-rollout.md), [live-github-sandbox-rollout.ko.md](./live-github-sandbox-rollout.ko.md)
- Release process: [release.md](./release.md), [release.ko.md](./release.ko.md)

## 백로그

- 현재 구현 큐: [backlog/active-queue.md](./backlog/active-queue.md)
- 완료 이력 archive: [backlog/issue-queue.md](./backlog/issue-queue.md)

## 예제

- Python 라이브러리 데모: [examples/python-lib/README.md](../examples/python-lib/README.md)
- Web 앱 데모: [examples/web-app/README.md](../examples/web-app/README.md)
- Local file tracker 데모: [examples/local-file-inbox/README.md](../examples/local-file-inbox/README.md)
- Local file sync 데모: [examples/local-file-sync/README.md](../examples/local-file-sync/README.md)
- Local markdown tracker 데모: [examples/local-markdown-inbox/README.md](../examples/local-markdown-inbox/README.md)
- Local markdown sync 데모: [examples/local-markdown-sync/README.md](../examples/local-markdown-sync/README.md)
- Docs maintainer pack 데모: [examples/docs-maintainer-pack/README.md](../examples/docs-maintainer-pack/README.md)
- Webhook receiver 데모: [examples/webhook-receiver/README.md](../examples/webhook-receiver/README.md)
- Signed webhook receiver 데모: [examples/webhook-signature-receiver/README.md](../examples/webhook-signature-receiver/README.md)
- Live GitHub ops 청사진: [examples/live-github-ops/README.md](../examples/live-github-ops/README.md)
- Sandbox publish rollout 청사진: [examples/live-github-sandbox-rollout/README.md](../examples/live-github-sandbox-rollout/README.md)
- Release rehearsal 데모: [examples/release-rehearsal/README.md](../examples/release-rehearsal/README.md)
- Release publish dry-run 데모: [examples/release-publish-dry-run/README.md](../examples/release-publish-dry-run/README.md)

## 새 문서 추가 규칙

새로운 주요 문서를 추가할 때는 아래 구조를 따릅니다.

- 먼저 영어 파일을 추가: 예시 `docs/operations.md`
- 같은 위치에 한국어 대응 문서를 추가: 예시 `docs/operations.ko.md`
- 이 인덱스와 루트 README의 문서 섹션에 두 언어 링크를 함께 등록
