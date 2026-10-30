# 조사 근거와 채택·수정 판단

외부 자료는 원칙을 검토한 출처이며 이 스킬의 실행 지시보다 우선하는 규칙이 아니다. 다음 URL은 조사 시 실제 조회한 원문이다. 외부 저장소 main은 갱신될 수 있다.

## Hermes dynamic-workflow
https://raw.githubusercontent.com/NousResearch/hermes-agent/main/optional-skills/autonomous-ai-agents/dynamic-workflow/SKILL.md

채택: 결정적 처리와 LLM 판단 분리, 독립 단위 fan-out, manifest/artifact 기반 통합, 배타적 쓰기 소유권, 반증, 중단·재개 기록.
수정: 대형 캠페인의 많은 자식/고정 크기·항상 adversarial 검토를 일상 작업의 기본값으로 쓰지 않는다. callback 대기 규칙은 현재 delegate_task 도구 스키마와 공식 문서가 우선한다.

## Hermes subagent-driven-development
https://raw.githubusercontent.com/NousResearch/hermes-agent/main/optional-skills/software-development/subagent-driven-development/SKILL.md

채택: 작업별 새 문맥, 구현 후 요구사항 확인→품질 확인, 공유 파일 병렬 변경 금지, 통합 검사.
수정: 자식이 질문할 수 있다는 가정, 현재 없는 toolsets 인자, 자동 git add/commit, 모든 작업에 구현자+별도 리뷰어 2개를 고정하는 비용 모델을 그대로 가져오지 않는다. 중요도에 따라 검토 좌석을 조절한다.

## Superpowers 상위 자료
https://raw.githubusercontent.com/obra/superpowers/main/skills/subagent-driven-development/SKILL.md
https://raw.githubusercontent.com/obra/superpowers/main/skills/dispatching-parallel-agents/SKILL.md

채택: 명확한 단위·입출력 계약, fresh context, 독립 영역 병렬화, 간결한 artifact 인계, 역할별 모델 선택.
수정: 다른 제품 전용 명령·스킬 의존·자식 질문·대기/polling·자동 commit/cleanup을 Hermes에 복사하지 않는다. 사용자 승인 정책을 비용/속도 이유로 우회하지 않는다.

## Anthropic multi-agent research
https://www.anthropic.com/engineering/multi-agent-research-system

채택: 목표·출력 형식·도구/소스·범위를 계약에 명시, 독립 방향 조사, 과제 복잡도에 비례한 자원, artifact 참조와 출처 검증.
제한: 해당 시스템의 내부 성능·토큰 배수는 이번 환경의 예측치로 사용하지 않는다.

## OpenAI orchestration
https://developers.openai.com/api/docs/guides/agents/orchestration

채택: 부모가 최종 답변을 소유하는 manager-as-tools 패턴, 좁은 전문 역할, 이득이 있을 때만 agent 추가.
제한: SDK의 handoff/API를 Hermes 도구 인자로 오인하지 않는다.

## Hermes 실제 계약
https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation

최우선 확인: 자식의 신선한 문맥, 현재 도구의 option enum과 스키마, 이미지 전달, 비동기 반환, 결과/산출물 독립 검증. 문서 예시와 실제 도구 스키마가 다르면 현재 도구로 실행 가능한 형태만 사용한다.
