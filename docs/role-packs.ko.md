# Role Pack 예제

RepoAgents는 core role pipeline을 작게 유지하지만, `roles.enabled`를 확장해서 optional built-in role을 활성화할 수 있습니다.

## 현재 built-in role pack

### QA gate

목적:

- engineering과 review 사이에 명시적인 QA 단계를 추가
- reviewer 승인 전에 validation gap을 드러냄
- mock backend 데모에서도 결정적 동작 유지

설정 예시:

```yaml
roles:
  enabled:
    - triage
    - planner
    - engineer
    - qa
    - reviewer
```

달라지는 점:

- `qa`가 engineer 결과와 review signal을 입력으로 받음
- `qa.json`, `qa.md` artifact를 남김
- reviewer가 extra role result를 참고해 최종 결정을 내릴 수 있음

바로 실행 가능한 예제:

- [examples/qa-role-pack/README.md](../examples/qa-role-pack/README.md)
- [scripts/demo_qa_role_pack.sh](../scripts/demo_qa_role_pack.sh)

## repo-local custom maintainer pack

새 runtime role 이름이 없어도 custom pack을 만들 수 있습니다.

실용적인 custom pack은 다음처럼 구성할 수 있습니다.

- core role 순서는 유지
- `.ai-repoagents/roles/*.md` override
- 필요한 `.ai-repoagents/prompts/*.txt.j2` override
- `.ai-repoagents/policies/*.md` override
- `AGENTS.md`에 repo-specific instruction 추가

### Docs maintainer pack

목적:

- documentation-first 저장소에 맞게 기본 pipeline을 더 날카롭게 조정
- 범위를 Markdown, quickstart, reference docs 안에 유지
- `repoagents init` 이후 repo가 자체 role/prompt/policy override 번들을 얹는 방식을 예시화

바로 실행 가능한 예제:

- [examples/docs-maintainer-pack/README.md](../examples/docs-maintainer-pack/README.md)
- [scripts/demo_docs_maintainer_pack.sh](../scripts/demo_docs_maintainer_pack.sh)

## 어떤 role pack을 쓸지

기본 4-role 경로가 적합한 경우:

- 가장 단순한 maintainer loop가 필요할 때
- 추가 validation 단계가 필요 없을 때

QA gate pack이 적합한 경우:

- 코드 변경에 대해 명시적인 테스트/coverage checkpoint가 필요할 때
- engineering output과 validation guidance를 분리된 artifact로 남기고 싶을 때
- custom role을 추가하기 전에 optional built-in role 동작을 평가하고 싶을 때

repo-local custom maintainer pack이 적합한 경우:

- Python runtime 코드는 바꾸지 않고, 저장소별 프롬프트와 정책만 더 정교하게 만들고 싶을 때
- 기본 4-role pipeline은 충분하지만 instruction을 더 날카롭게 조정해야 할 때
- 새 built-in role을 만들기 전에 도메인 특화 pack을 먼저 검증하고 싶을 때

## 제약

- core 순서는 `triage -> planner -> engineer -> reviewer`를 유지해야 함
- `qa`는 `engineer`와 `reviewer` 사이에만 넣을 수 있음
- 중복 role 이름은 허용되지 않음

## 이후 role pack

현재 코드베이스는 다음 같은 built-in/custom 예제로 확장할 준비가 되어 있습니다.

- `security-review`
- `docs-editor`
- `release-manager`

이들도 같은 패턴을 따릅니다. role class를 추가하고, registry에 노출하고, config sequence를 문서화하고, runnable example을 제공하면 됩니다.
