---
name: subagent-orchestration
description: "Use when delegating tasks. Route, brief, verify workers."
version: 0.2.0
author: BCL, Hermes Agent
license: Apache-2.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [delegation, orchestration, routing, cost, verification]
    related_skills: [hermes-agent, requesting-code-review]
---

# 비용·근거 중심 서브에이전트 운영 (Hermes 어댑터)

이 스킬은 에이전트 중립 정책을 Hermes의 `delegate_task`에 적용하는 얇은 어댑터입니다. 정책 본문은 `references/orchestration-policy.md`, 티어와 변형의 연결은 `references/routing-policy.md`, 인계 양식은 `templates/task-contract.md`에 있습니다. 위임을 시작하기 전에 정책 본문을 읽으십시오. 이 스킬은 행동 지침이며 런타임 라우터, 권한 통제, 지출 제한을 강제하지 않습니다.

## When to Use

- 독립 조사, 분석, 구현, 검토를 `delegate_task`로 맡길 때.
- 작업 난도와 비용에 맞는 변형, 병렬 범위, 승격 경로를 고를 때.
- 단일 조회, 산술, 반복 파싱, 순차 의존 작업에는 에이전트를 만들지 말고 직접 도구나 `execute_code`를 쓰십시오.

## Hermes에서 확인할 것

- **경로는 `option`으로 고릅니다.** `option`은 `advanced-delegation` 플러그인의 `model_map`에 등록된 경로 이름이며, 현재 도구 스키마에 나열된 이름만 유효합니다. 제안 JSON, 과거 세션, 이 스킬의 표는 등록의 증거가 아닙니다.
- **작업 인자는 `tasks=[{goal, context, option, output_schema?, images?}]`입니다.** 도구가 받지 않는 `model`, `toolsets`, `reasoning_effort`, `service_tier`를 작업에 임의로 추가하지 마십시오.
- **`model_map`은 provider, model, base_url, api_key, api_mode, reasoning_effort, service_tier를 경로에 복사하고 fallback_providers를 선택적으로 전달합니다.** 그 밖의 라우터 옵션은 서브에이전트 경로에서 쓸 수 없다고 가정하십시오.
- **추론 강도를 생략하면 `delegation.reasoning_effort` 또는 부모 설정을 상속합니다.** 경로마다 지원하는 값이 다르므로 정확한 모델의 지원 집합으로 확인하십시오. `none`은 끄기이며 추론 필수 모델에는 쓸 수 없습니다.
- **현재 OpenRouter 경로는 `fast`/`ultrafast`를 받지 않습니다.** 모든 제안 경로는 `service_tier: normal`입니다.
- **경로 목록은 세션 시작 시 스키마로 고정됩니다.** 설정을 바꾼 뒤에는 새 세션에서 경로를 다시 확인하십시오.
- **자식은 질문하거나 재위임할 수 없습니다.** 불명확한 요구는 추측 실행 대신 blocker로 반환하게 하십시오.
- **비동기 위임 결과는 턴 사이에 도착합니다.** 의존하지 않는 일만 하고 턴을 끝내십시오. transcript를 polling하지 마십시오. `/new`, `/stop`, 프로세스 종료는 실행 중인 자식을 중단시킵니다.
- **이미지는 `images`로 최대 8개까지 직접 전달됩니다.** 음성과 영상은 전사나 프레임 추출을 거쳐 텍스트나 이미지로 넘기십시오.
- **기존 경로로 한 검증은 신규 경로의 실호출 검증이 아닙니다.** 그렇게 보고하지 마십시오.

## Procedure

1. `references/orchestration-policy.md`의 절차 1~8을 따릅니다.
2. 경로 선택 시 `references/routing-policy.md`의 티어를 쓰고, 현재 `option` 목록과 정확히 대조합니다. 없으면 `activation_required`로 보고합니다.
3. 자식 계약은 `templates/task-contract.md`로 작성합니다.

## 동기화

`references/`와 `templates/`는 저장소의 `core/policy/`에서 생성된 사본입니다. 직접 고치지 말고 `core/policy/`를 고친 뒤 `python adapters/hermes/sync_skill.py`를 실행하십시오. 불일치 검사는 `--check`입니다.
