# 서브에이전트 활용 스킬 조사 및 라우팅 연동

## 현재 상태

현재 default 프로필에 사용자 로컬 스킬 `subagent-orchestration`을 등록하고 `skill_view`로 로드했다. 외부 스킬을 원본 그대로 설치한 것이 아니라, 내용을 검토해 현재 Hermes 계약과 비용 중심 티어에 맞게 작성한 절차 스킬이다. 다른 프로필은 변경하지 않았다. 스킬은 지침이며 자동 라우터/지출 hard cap/보안 강제 기능은 아니다.

모델 라우팅의 신규 17개 변형은 여전히 적용 전이다. 스킬은 문서상 제안과 현재 도구 enum을 구분하고, 미등록 경로를 호출하거나 기존 비슷한 이름으로 자동 대체하지 않게 한다. 현재 도구의 기존 경로를 활용한 읽기 전용 행동 검증은 신규 17개 경로의 추론·속도·실호출 검증과 별개다.

## 조사한 스킬·공식 자료

| 자료 | 채택한 노하우 | 그대로 가져오지 않은 부분 |
|---|---|---|
| Hermes dynamic-workflow | 결정적 처리/LLM 판단 분리, manifest·artifact, 비동기 수신, 반증, 쓰기 소유권 | 대형 캠페인 규모를 일상 작업에 기본 적용하지 않음 |
| Hermes subagent-driven-development | 작업별 새 문맥, 요구사항 확인→품질 확인, 통합 검증 | 현재 도구에 없는 인자, 자식 질문 가능성, 자동 commit, 모든 과제에 별도 두 리뷰어 강제 |
| Superpowers subagent-driven-development | 작업 계약, 역할별 적정 모델, 파일 인계, 반복 실패 통제 | 다른 제품 전용 도구·명령·대기 방식·자동 정리 |
| Superpowers dispatching-parallel-agents | 독립 범위만 병렬화, 명확한 목표·범위·결과, 충돌 확인 | 공유 상태를 무시한 병렬 구현 |
| Anthropic multi-agent research | 목표·출력·소스·경계 명시, 과제 난도에 비례한 노력, 부모 통합 | 타 시스템 성능·토큰 배수를 이번 환경의 예상 성과로 사용하지 않음 |
| OpenAI orchestration | manager-as-tools, 부모 최종 책임, 필요할 때만 전문 에이전트 추가 | SDK의 handoff를 Hermes 도구 인자로 오인하지 않음 |

Hermes 두 스킬의 실제 본문을 확인했다.[14][15] 원본 upstream 스킬도 비교했다.[12][13] Anthropic은 명시적 작업 계약과 난도에 맞는 자원 배분을 강조하며, OpenAI는 전문 에이전트를 이익이 있을 때 추가하고 부모가 최종 답변을 소유하는 패턴을 구분한다.[10][11]

## 이번 라우팅과의 연결

```text
사용자 목표
  → 직접 도구로 충분한가?
  → 독립 작업·의존성·쓰기 소유권 분석
  → L1/L2/M1/M2/F1/F2/F3 또는 E0/V1/V2 배정
  → 실제 활성 option + 모델·추론·속도 호환 확인
  → 목표·경계·검사·종료 조건이 있는 작업 계약
  → 실행·비동기 수신
  → 부모의 실제 근거 확인 + 필요 시 독립 리뷰
  → 원인별 수정/승격 또는 통합 완료
```

- 제안 경로와 실제 활성 경로 불일치 → activation_required. 숨은 치환 없음.
- 추론 생략/미지원 강도/미지원 속도 → 파라미터 문제 해결. 고가 모델 승격으로 숨기지 않음.
- 입력 누락 → brief 보완. 모델 실패로 오인하지 않음.
- 모델 판단 한계 → 근거를 붙여 유효한 깊은 변형 또는 상위 티어 선택.
- 무료 할당량 실패 → 유료 자동 전환 금지.
- 단순 결과 → 부모의 기계적 검사·표본 확인. 위험한 변경 → 독립 검토 강화.

현재 Hermes의 도구 스키마, 신선한 자식 문맥, 비동기 반환과 결과 확인 계약에 맞춘다.[3]

## 등록한 파일

- `SKILL.md`: 위임 필요성, 분해, 활성 경로 확인, 작업 계약, 실행, 검증, 원인별 승격, 재개 기록.
- `references/routing-policy.md`: 신규 17개 변형과 세부 티어 매핑. 활성 상태 아님을 명시.
- `templates/task-contract.md`: 목표·선행조건·쓰기 범위·근거·종료 조건·출력 계약.
- `references/research-basis.md`: 원문과 채택·수정 판단.
- 기존 hermes-agent 스킬의 해당 안내에 신규 운영 스킬 연결.

스킬이 현 세션에서 로드되는 것은 확인했다. 향후 세션에서의 자동 선택은 스킬 description/발견 기능에 의존하며 모든 턴의 강제 실행을 보장하는 hook은 설치하지 않았다.

## 검증

- 구조 검사: frontmatter 설명 길이, 참조 파일 존재, 신규 변형 17개의 정확한 경로명 매핑.
- 행동 검사: `orchestration-skill-cases.json`의 가상 상황 8개를 독립 검토자가 스킬을 읽고 판단한다.
- 별도 독립 검토자가 같은 스킬의 모호한 규칙·위험한 과잉 위임·옵션 실수 가능성을 검사한다. 비용 절약을 위해 행동 검사와 같은 1개 자식에게 묶는다.
- 이 검사는 실제 읽기 전용 자식 호출을 사용하되, 신규 라우팅·실제 외부 변경·실제 배포를 수행하지 않는다.
- 상태: 스킬 등록/로드/구조 검증 완료. 기존 활성 Luna 경로를 통한 독립 행동 검사도 완료했다.
- 결과: 가상 상황 8개 모두 부모의 기대 판단과 일치했다. 중복/누락 없이 8개 case_id를 프로그램으로 대조했다. 독립 검토자는 중요한 결함을 보고하지 않았다.
- 확인 내용: 직접 도구 선택, 독립 읽기 병렬화, 공유 쓰기 직렬화, 미활성 경로 차단, 미지원 옵션 거부, 무료→유료 우회 금지, 고위험 독립 검토, 파괴적·외부 변경 승인 요구.
- 실제 검토 호출: `Middle-Agent-GPT-6-Luna` / `openai/gpt-6-luna`, 보고된 API 호출 3회·소요 18.34초. 신규 17개 경로를 실행한 결과가 아니다.
- 근거 파일: `orchestration-skill-validation.json`. 소규모 가상 상황 검사이며 실무 성공률·절감액을 입증하지 않는다. 리뷰어의 결함 미발견은 결함 부재 보증이 아니다.

## 지금 달성한 것 → 다음 단계

외부 활용 스킬 조사·현재 환경에 맞춘 운영 스킬 등록·티어와 17개 변형 연결 → 행동 판단과 독립 검토 결과 반영 후 신규 라우팅의 별도 실호출/활성화 검증.

## Sources

[3] https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
[10] https://www.anthropic.com/engineering/multi-agent-research-system
[11] https://developers.openai.com/api/docs/guides/agents/orchestration
[12] https://raw.githubusercontent.com/obra/superpowers/main/skills/subagent-driven-development/SKILL.md
[13] https://raw.githubusercontent.com/obra/superpowers/main/skills/dispatching-parallel-agents/SKILL.md
[14] https://raw.githubusercontent.com/NousResearch/hermes-agent/main/optional-skills/autonomous-ai-agents/dynamic-workflow/SKILL.md
[15] https://raw.githubusercontent.com/NousResearch/hermes-agent/main/optional-skills/software-development/subagent-driven-development/SKILL.md
