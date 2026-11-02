# OpenRouter 서브에이전트: 모델 × 작업용 변형 재구성안

## 현재 단계와 범위

2026-10-30. 모델 목록 중심 v1을 폐기하고 모델 × 변형 × 적용 조건 중심으로 개정했다. 현재 단계: 정적 호환성·설정 변환 검증 완료, 실호출 및 적용 전. default 프로필의 운영 설정은 변경하지 않았다. 다른 Hermes 프로필·대화·기억·스킬은 초기화하지 않는다.
Pro 명칭은 제외 기준이 아니다. Kimi Pro 비선호 이유는 작업 난도 대비 가성비였다. 모든 모델은 성공한 작업당 총비용으로 판단한다. 변형은 별도 계정/프로필이 아니라 model_map 경로다.

## 부모 모델과 실행자의 판단 분담

부모는 라우팅·종합 판단이 강한 고성능 모델을 사용하는 구조를 권장한다. 이번 역할 설계만 반영하며 부모 모델 설정 자체는 변경하지 않는다.

- 부모 전담: 목표 해석·작업 분해·티어/변형 선택·자원 배분·모순 판정·승격/중단·완료 승인·최종 답변.
- 자식 담당: 계약 내 조사·코드 작성·자료 처리·도구 선택·자기 검사. 근거·검사 결과·대안·불확실성·blocker를 반환.
- 자식이 부모에게 올릴 것: 목표/쓰기 범위/위험/예산 변경, 주요 근거 충돌, 구조적 실패. 매 도구 호출과 작은 구현 판단까지 부모가 재승인하지 않는다.
- 부모가 고성능이어도 어려운 실행을 무조건 최저가 모델에 맡기지 않는다. 과제 수행에 필요한 능력과 성공 작업당 비용을 기준으로 실행자를 선택한다.
- 고가 판단 전담 자식을 모든 작업에 추가하지 않는다. F1/F2는 전문 작업·새 문맥의 이익·독립 검토가 필요할 때만 호출한다.
- 부모의 결과 수용은 별도 고위험 독립 검토를 대체하지 않는다. 실제 산출물·테스트·원문·외부 target 상태를 확인한다.
- 부모 모델 후보는 라우팅 정확성, 도구/JSON 스키마 준수, 지시 이행, 긴 문맥 유지, 잘못된 자식 결과 거부, 불필요한 위임 억제, 전체 비용을 같은 과제로 평가한다. 단일 추론 점수만으로 선정하지 않는다.

권장 흐름: 고성능 부모의 계획·배정 → 적정 비용 자식의 실행 → 간결한 근거/산출물 인계 → 부모의 수용·재배정 판단 → 위험에 따른 독립 검토 → 최종 통합.

## 설계의 핵심 수정

1. **생략은 기본값 보장이 아니다.** 설치된 `tools/delegate_tool_config.py::_child_reasoning`은 경로 effort → delegation 전역 effort → 부모 reasoning_config 순으로 상속한다. 따라서 reasoning_effort가 빠진 경로를 안전한 네이티브 기본값으로 표시하지 않는다.
2. **추론 강도와 가속 서비스는 다르다.** low는 사고량을 낮추려는 설정이지 fast 서비스 구매가 아니다. 현재 설치된 Hermes `hermes_cli/models.py::_fast_mode_route_supported`는 일반 OpenRouter 경로의 fast/ultrafast를 허용하지 않는다. 모든 실행 제안에는 `service_tier: normal`을 명시한다. 이는 부모의 priority/speed 상속 제거이며, OpenRouter 내부 provider가 반드시 특정 표준 endpoint로 고정된다는 뜻은 아니다.
3. **강도 선택 미공개 모델을 임의의 Deep/Quick으로 복제하지 않는다.** Qwen Flash·MiMo Flash·무료 Nemotron VL은 공개 목록에 reasoning은 있지만 supported_efforts가 없다. 명시적인 추론 끄기만 선택한 제한형 변형으로 두고, 추론 켜기/네이티브 기본 모드는 별도 호환성 검증 전 보류한다.[1][6]
4. **none은 자동이 아니라 추론 끄기다.** Hermes는 none을 reasoning.enabled=false로 변환한다. 추론 필수 모델에는 none을 쓰지 않는다. none 경로의 첫 응답·도구 왕복 실호출은 아직 미검증이다.[6]
5. **표에 적힌 속도는 목표다.** 저지연 지향/균형/정확성 우선은 사용 목적이며 실측 초·tokens/s를 뜻하지 않는다. 짧은 사고가 항상 짧은 완료시간을 보장하지 않는다.

## 운영 티어 세분화 제안 — 모델 서열과 호출 정책의 분리

이 절은 티어 체계에 대한 개정 제안이다. 기존 호출 경로명·reasoning_effort·service_tier 및 운영 설정은 바꾸지 않는다. 티어는 모델 전체의 고정 등급이 아니라 작업별 변형에 붙이는 배정 정책으로 사용한다. 다음 역할 분류는 권장 운영 가설이며 성능 실측 결과가 아니다.

| 대분류 | 세부 티어 | 배정 기준 | 기존 변형의 배치 예 |
|---|---|---|---|
| 프론티어 | F1 전문 작업 | 미들티어로 부족한 복잡한 설계·다중 파일 구현·교차검증 | Sol-Standard, Sonnet-Code; 오픈웨이트(가성비): GLM-Standard, DeepSeek-Standard, Qwen-Standard |
| 프론티어 | F2 난제 해결 | 미들티어/전문 작업 실패 또는 처음부터 실패 비용이 큰 난제 | Sol-Deep, Sonnet-Debug; 오픈웨이트(가성비): GLM-Deep, DeepSeek-Deep, Qwen-Deep |
| 프론티어 | F3 예외 투입 | 비용·지연 증가를 감수할 근거가 있는 최고 난도. 기본 경로 제외 | 예비 Opus-Deep; Kimi는 비교 결과에 따라 F1/F2 배정 가능 |
| 미들티어 | M1 일반 실행 | 목표와 완료 조건이 명확한 다단계 조사·구현·분석 | Haiku-Balanced, Terra-Quick/Balanced |
| 미들티어 | M2 심층 실행 | 조건 충돌·원인 분석·긴 문서 논리 검토. 프론티어 전 마지막 단계 | Terra-Deep, DeepSeekPro-Reason |
| 로우티어 | L1 추출·변환 | 정답 형식과 검사 기준이 명확한 좁은 작업 | GLM-Extract, Qwen-Lite |
| 로우티어 | L2 제한적 실행 | 변경 대상과 테스트가 명확한 작은 수정·정해진 절차 실행 | Haiku-Quick, DeepSeekPro-Plain |
| 프리티어 | E0 실험 | 지연·실패를 허용하는 평가/탐색. 유료 자동 승격 없음 | Free-Nemotron-Visual |
| 멀티모달 | V1 지각·판독 | 글자·객체·차트 값·화면 상태 판독 | MiMo-Inspect, Gemini-Inspect |
| 멀티모달 | V2 시각 추론 | 여러 시각 자료 관계·모순·원인 추론 | Gemini-Reason; Kimi 시각 변형은 비교 검증 후 배정 |

### 세분화 원칙

- F/M/L은 실행 난도·자원 투입 정책, E0는 무료 실험 정책, V1/V2는 입력·작업 유형이다. 이들은 완전히 같은 축이 아니다. 시각 모델에도 비용·난도 수준을 별도 태그로 표시하고, 무료 모델을 유료 계층의 최하단 성능으로 간주하지 않는다.
- 처음부터 모든 세부 티어를 별도 호출 경로로 만들지 않는다. 기존 변형에 세부 티어를 매핑하고, 모델/추론/실제 경로가 같다면 이름만 다른 중복 변형을 추가하지 않는다.
- L2라는 이유만으로 쓰기 권한을 주거나 F2라는 이유만으로 검증을 생략하지 않는다. 쓰기 범위·승인·검증 정책은 티어와 별개로 유지한다.
- 추론 강도는 티어의 숫자와 동일하지 않다. 모델별 지원 집합과 작업 필요로 결정한다. DeepSeek Pro의 high가 M2에 있어도 다른 모델의 high와 동일한 사고량·품질을 보장하지 않는다.
- 속도는 별도 속성으로 유지한다. 저지연 지향/균형/지연 허용은 목표이며 API 속도 옵션은 기존 normal을 유지한다. 미지원 fast/ultrafast를 추가하지 않는다.
- 비용 상한은 티어 이름만으로 정하지 않는다. 추론·도구 왕복·긴 입력 할증을 포함한 성공 작업당 실측비용을 모은 뒤, 입력 규모와 작업 유형별로 정한다.

### 승격·진입 규칙

1. 단순 추출/변환은 L1, 작고 검증 가능한 수정은 L2, 일반 다단계 작업은 M1에서 시작한다. 모든 작업을 최저 티어에 먼저 맡기지는 않는다.
2. 논리적 복잡성 증가 또는 모델 한계로 인한 실패는 M2 → F1/F2로 승격한다. 문맥 누락·도구 오류·권한 문제는 모델 승격 대신 해당 원인을 해결한다.
3. 처음부터 영향이 큰 설계·고위험 검토는 F1/F2로 바로 진입할 수 있다. F3는 예상 재작업 감소가 추가 비용을 정당화할 때만 예외적으로 선택한다.
4. E0와 V1/V2는 별도 분기다. 무료 실패를 유료로 자동 승격하지 않으며, 시각 판독 실패를 텍스트 모델의 높은 추론 강도로 해결하려 하지 않는다.
5. 문서 길이·이미지 수·변경 범위·완료 조건이 달라지면 동일 모델의 변형과 세부 티어를 재선택한다.

## 서브에이전트 운영 스킬과의 연동

현재 default 프로필에 `subagent-orchestration` 스킬을 등록하고 로드했다. 조사·채택 근거는 같은 폴더의 `subagent-orchestration-research.md`에 기록했다. 외부 스킬을 무검토 일괄 설치하지 않았으며 현재 도구 계약과 비용 정책에 맞춘 절차 스킬이다.

- 스킬: 위임 필요성 판단 → 작업 분해/쓰기 소유권 → 티어/변형 선택 → 실제 활성 option 확인 → 작업 계약 → 실행 → 부모 근거 확인 → 원인별 수정/승격.
- 라우팅: 어느 모델·추론·속도 경로를 실제 호출할 수 있는지 정의한다. 스킬은 이를 대신 활성화하지 않는다.
- 활성 상태: 스킬 등록·로드 완료. 신규 17개 model_map은 아직 적용 전이다. 스킬은 미등록 경로 호출과 유사한 과거 이름으로의 숨은 치환을 금지한다.
- 비용 정책: 단순 처리는 직접 도구, 독립 작업만 병렬화, 같은 형태의 작은 작업은 묶기, 고위험에 독립 리뷰 집중, 무료→유료 자동 전환 금지.
- 검증: 스킬 구조·정확한 경로명 연결을 확인했고, 기존 활성 Luna 경로 1개로 읽기 전용 가상 상황 8개 판단을 실행하여 부모의 기대 판단과 모두 일치함을 확인했다. 독립 검토에서 중요한 결함은 보고되지 않았다. `orchestration-skill-validation.json` 참조. 이는 신규 모델 옵션 실호출 검증이나 실무 성능 보증이 아니다.

## 실행 후보: 23개 변형 / 13개 모델

모든 변형의 속도 옵션은 normal, 유료/다른 모델 자동 폴백은 없음이다. 추천 기본값은 M-Haiku-Balanced(입력 100K 미만)이며 긴 입력은 부모가 다른 경로를 명시적으로 선택한다. 이하 배정은 실무 가설이고 성능 검증 결과가 아니다.

| 티어 | 변형 경로 | 추론 | 속도 목표 | 언제 사용 | 사용하지 말 것 |
|---|---|---|---|---|---|
| 프론티어 | `F-Sol-Standard` | medium | 균형 | 어려운 설계·근거 교차검증. 미들티어로 부족하지만 최대 추론까지 불필요한 작업 | 짧은 요약·단순 추출 |
| 프론티어 | `F-Sol-Deep` | high | 정확성 우선 | 상충하는 제약·난해한 원인 분석·실패 비용이 큰 최종 검토 | 동일 과제 반복 재시도·시간 민감 단순 작업 |
| 프론티어 | `F-Sonnet-Code` | medium | 균형 | 여러 파일 구현·리팩터링·코드 리뷰. 작은 모델 실패 후 사용 | 한 줄 수정·대량 문서 정리 |
| 프론티어 | `F-Sonnet-Debug` | high | 정확성 우선 | 재현이 어려운 버그·복잡한 코드 경로·설계 결함 분석 | 범위가 좁은 기계적 코드 변경 |
| 프론티어(오픈웨이트) | `F-GLM-Standard` | high | 균형 | 에이전트형 코딩·장기 도구 사용·여러 파일 구현을 낮은 단가로. 추론 끄기 불가 | 이미지 입력·짧은 요약·추론 없이 처리할 작업 |
| 프론티어(오픈웨이트) | `F-GLM-Deep` | max | 정확성 우선 | F-GLM-Standard 로 부족한 난해한 디버깅·설계 결함 분석. 추론 끄기 불가 | 이미지 입력·동일 과제 반복 재시도·좁은 기계적 변경 |
| 프론티어(오픈웨이트) | `F-DeepSeek-Standard` | high | 균형 | 긴 문서 논리 검토·여러 파일 구현·교차검증을 낮은 단가로. 텍스트 입력만 | 이미지 입력·짧은 요약·단순 추출 |
| 프론티어(오픈웨이트) | `F-DeepSeek-Deep` | max | 정확성 우선 | 난해한 원인 분석·실패 비용이 큰 검토 중 F-DeepSeek-Standard 로 부족한 경우. 텍스트 입력만 | 이미지 입력·동일 과제 반복 재시도·시간 민감 단순 작업 |
| 프론티어(오픈웨이트) | `F-Qwen-Standard` | medium | 균형 | 어려운 설계·근거 교차검증·코드 리뷰(2.4T 파라미터 오픈웨이트). 추론 끄기 불가 | 이미지 입력·짧은 요약·단순 추출 |
| 프론티어(오픈웨이트) | `F-Qwen-Deep` | xhigh | 정확성 우선 | 상충하는 제약·고위험 독립 검토 중 F-Qwen-Standard 로 부족한 경우. 추론 끄기 불가 | 이미지 입력·동일 과제 반복 재시도·시간 민감 단순 작업 |
| 미들티어 | `M-Terra-Quick` | low | 저지연 지향 | 명확한 조건의 코드 탐색·일반 조사·작은 구현 | 불명확한 아키텍처·보안 최종 검토 |
| 미들티어 | `M-Terra-Balanced` | medium | 균형 | 일반 다단계 구현·문서와 코드 종합 분석 | 단순 분류·최고 난도 최종 판정 |
| 미들티어 | `M-Terra-Deep` | high | 정확성 우선 | 다수 제약·실패 원인 분석. 프론티어 승격 직전 단계 | 상시 기본값·대량 요약 |
| 미들티어 | `M-DeepSeekPro-Plain` | none | 저지연 지향 | 명확한 요구사항의 코드 작성·형식 변환. 고급 모델을 비추론 모드로 비교할 실험 | 복잡한 설계·추론을 끈 상태의 난제 |
| 미들티어 | `M-DeepSeekPro-Reason` | high | 정확성 우선 | 비용 제한을 고려한 깊은 코드 분석·구현·긴 문서의 논리 검토 | 추출·대량 분류. medium/low를 이 모델에 설정하지 말 것 |
| 미들티어 | `M-Haiku-Quick` | low | 저지연 지향 | 입력 100K 미만의 검색 정리·요약·명확한 작은 수정 | 100K 이상 긴 입력·어려운 추론 |
| 미들티어 | `M-Haiku-Balanced` | medium | 균형 | 기본 경로. 입력 100K 미만 일반 조사·작은 구현. 긴 입력이면 다른 경로 선택 | 100K 이상 무조건 배정·고위험 최종 판단 |
| 미들티어 | `M-Qwen-Lite` | none | 저지연 지향 | 긴 자료의 단순 정리·비전 포함 추출. 추론 선택 미공개이므로 명시적으로 추론 끔 | 지원 미확인 low/medium/high 지정·깊은 추론 |
| 로우티어 | `L-GLM-Extract` | low | 저지연 지향 | 범위가 좁은 추출·분류·형식 변환·간단한 수정. 부모가 결과 확인 | none/medium 임의 설정·중요한 무검증 변경 |
| 프리티어 | `Free-Nemotron-Visual` | none | 지연 허용 | 무료 이미지·텍스트 추출 실험. 추론을 명시적으로 끔. 유료 폴백 없음 | 납기 민감·개인정보·고위험 판단 |
| 멀티모달 | `MM-MiMo-Inspect` | none | 저지연 지향 | 단순 화면·차트·이미지 내용 추출. 추론 강도 미공개여서 추론 끔 | 깊은 시각 추론·직접 음성/영상 전달 가정 |
| 멀티모달 | `MM-Gemini-Inspect` | low | 저지연 지향 | 저가 시각 모델이 놓친 복잡한 차트·문서·화면 분석 | 대량 단순 OCR·고급 추론을 요구하는 복합 도표 |
| 멀티모달 | `MM-Gemini-Reason` | high | 정확성 우선 | 여러 도표·이미지의 관계 추론·시각적 모순 검증 | 단순 이미지 설명·비용 제한 없는 장시간 분석 |

## 모델 ID·가격·지원 추론 강도

가격은 USD / 100만 토큰 입력·출력, 비캐시 일반 모델 목록 기준. 업체별 단가·할인·긴 문맥 할증은 별도다. 같은 모델의 변형은 기본 단가가 같아도 소비 추론 토큰·도구 왕복 수가 달라 총비용이 달라진다. 추론 토큰은 출력 비용으로 청구된다.[1][6]

| 모델 ID | 입력 / 출력 | 공개된 강도 | 정책 |
|---|---:|---|---|
| `openai/gpt-6.1-sol` | $2 / $10 | max/xhigh/high/medium/low | 추론 필수 |
| `anthropic/claude-sonnet-5.5` | $2 / $10 | max/xhigh/high/medium/low | 추론 필수 |
| `openai/gpt-6.1-terra` | $1 / $5 | max/xhigh/high/medium/low/none | 추론 끄기 가능(실호출 검증 전) |
| `deepseek/deepseek-v4-pro` | $0.816234 / $1.63247 | xhigh/high/none | 추론 끄기 가능(실호출 검증 전) |
| `anthropic/claude-haiku-5.5` | $0.1 / $0.5 | max/xhigh/high/medium/low/none | 추론 끄기 가능(실호출 검증 전) |
| `qwen/qwen3.8-flash` | $0.15 / $0.47 | 선택 강도 미공개 | 추론 끄기 가능(실호출 검증 전) |
| `z-ai/glm-5.3-flash` | $0.0497 / $0.0701 | max/high/low | 추론 필수 |
| `nvidia/nemotron-3.5-super-vl:free` | $0 / $0 | 선택 강도 미공개 | 추론 끄기 가능(실호출 검증 전) |
| `xiaomi/mimo-v2.6-flash` | $0.14 / $0.28 | 선택 강도 미공개 | 추론 끄기 가능(실호출 검증 전) |
| `google/gemini-4-argon` | $2 / $10 | high/medium/low | 추론 필수 |

Haiku는 100K 이상 입력 시 $0.50/$2.50으로 할증된다. Sol·Terra는 272K 입력 기준 할증이 있으므로 긴 컨텍스트와 저렴한 문서 처리를 혼동하지 않는다. GLM Flash와 DeepSeek Pro는 특히 provider별 단가 편차를 확인해야 한다.[1]
Haiku와 Sonnet은 설치된 OpenRouter 어댑터에서 reasoning.effort 대신 top-level verbosity로 강도를 전달하는 분기가 있다. API body를 자체 제작할 때 Hermes 설정 키를 그대로 전송하는 방식으로 검증했다고 주장하지 않는다.

## Kimi Pro 등 예비 변형

| 변형 | 모델 | 추론 | 속도 | 사용 조건 / 보류 이유 |
|---|---|---|---|---|
| Reserve-Kimi-Visual | moonshotai/kimi-k3.1-pro | high | normal | 긴 시각/코드 복합 과제에서 Sol/Sonnet 대비 재작업을 줄이는지 확인할 때. 입력 $2/출력 $10 |
| Reserve-Kimi-Quick | moonshotai/kimi-k3.1-pro | low | normal | 비싼 모델의 사고량을 줄여도 작업 이점이 유지되는지 비교할 때. 저가 작업의 기본값으로 사용 금지 |
| Reserve-Opus-Deep | anthropic/claude-opus-5.5 | high | normal | 실패 비용이 큰 최난도 작업에서만. 입력 $4/출력 $20 |
| Reserve-DeepSeekFlash-Low/High | deepseek/deepseek-v4.1-flash-1017 | low / high | normal | 저비용 도구 작업 비교군. medium이 공개 강도 목록에 없으므로 중간값을 발명하지 말 것 |
| Hold-MiMoPro-Native | xiaomi/mimo-v2.6-pro | 네이티브 모드 격리 미확인 | normal | 이름이 Pro라서 제외하는 것이 아니다. 강도 미공개·상속 차단·기본 추론 모드 검증이 선행되어야 함 |
| Hold-Flint-Native | recursive/flint-v1.0:free | 필수 추론, 강도 미공개 | normal | none으로 끌 수 없고 생략하면 상속되므로 네이티브 기본값 격리 경로 확인 전 보류 |
| Hold-Qwen-Deep / MiMo-Deep / Omni-Deep | 각 Flash 모델 | 미확인 | normal | reasoning 지원과 low/medium/high 선택 지원은 별개. 가짜 변형을 등록하지 말 것 |
Kimi의 표준 endpoint는 $2/$10, 별도 highspeed endpoint는 $4/$20이다. 그러나 OpenRouter에 highspeed endpoint가 있다는 사실과 Hermes model_map의 service_tier:fast 사용 가능 여부는 별개다. 이번 제안에는 Highspeed 변형을 등록하지 않는다.[8]
DeepSeek V4 Pro는 표준 목록상 약 $0.816/$1.632다. 정확한 ID 엔드포인트에서 도구 지원을 확인하여 Pro 배제 없이 미들티어 추론 후보로 편입했다. 가격이 싸다는 이유로 성능 동등성을 가정하지는 않는다.[1][9]

## 속도 옵션을 다루는 정책

- `service_tier: normal`: 현 설치에서 허용되는 상속 차단용 설정. 이번 제안의 공통값이다.
- `service_tier: fast/ultrafast`: OpenRouter 경로에서는 현 Hermes 게이트와 맞지 않아 금지한다. 다른 provider에서 가능한 옵션을 그대로 옮기지 않는다.
- OpenRouter provider.sort=latency/throughput 및 endpoint only는 별도의 라우팅 제어다. low reasoning과도 별개다. 라우팅은 속도를 선호할 뿐 SLA를 보장하지 않는다.[7]
- 현재 advanced-delegation model_map의 ROUTE_FIELDS에는 extra_body/provider_preferences/request_overrides가 없다. 여기에 임의의 provider.sort JSON을 넣어도 전달되지 않으므로 설정 파일에 가짜 필드를 추가하지 않는다. 실제 속도 기반 endpoint 변형은 지원되는 provider 경로 또는 플러그인 확장 설계·검증이 필요하며 이번에는 코어/플러그인을 수정하지 않았다.
- 최초 토큰까지 시간(TTFT), 가시 출력 tokens/s, 전체 완료시간, 도구 왕복 수, 재시도를 따로 측정한다. 이번 공개 endpoint 응답에는 비교 가능한 latency/throughput 수치가 없어 임의의 초·속도 배수를 쓰지 않는다.

## 작업 선택·승격 규칙

1. 단순 추출/변환 → L-GLM-Extract. 실패가 문맥/추론 문제이면 Haiku/Terra로 승격한다.
2. 짧은 일반 작업 → M-Haiku-Quick 또는 Balanced. 100K 이상이면 Qwen-Lite(단순) 또는 DeepSeekPro-Reason/Terra(추론)로 분기한다.
3. 일반 구현 → Terra-Quick/Balanced. 조건 충돌·원인 분석이 추가되면 같은 모델 Deep으로 한 단계 올린다.
4. 비용 민감한 깊은 코드 작업 → DeepSeekPro-Reason과 Terra-Deep을 비교한다. 실패 시 반복 소모하지 말고 Sonnet-Debug/Sol-Deep으로 승격한다.
5. 시각 추출 → MiMo-Inspect 또는 무료 Nemotron. 복잡한 시각 관계는 Gemini-Inspect/Reason. Hermes의 직접 미디어 전달은 이미지 최대 8개이며 음성/영상은 별도 전처리·도구 경로가 필요하다.[3]
6. 비싼 모델은 저가 모델의 반복 실패 비용을 줄일 때만 채택한다. Kimi는 Pro 명칭으로 제외하지 않되 이 개선을 실측하기 전 상시 기본값으로 두지 않는다.
7. 무료 실패는 유료 자동 전환하지 않는다. 무료 요청 제한 때문에 무료 티어에 납기를 의존하지 않는다.[2]

## 검증 결과와 남은 인수 조건

- 오프라인 검사 17개 통과: 모델/강도/필수 추론/속도/기본값/필드 화이트리스트 + 설치된 none·normal 설정 변환 + 상속 함수 재현. `variant-validation.json` 참조.
- 검증한 부정 사례: Kimi medium, DeepSeek Pro medium, GLM Flash medium/none, Qwen/MiMo 임의 high/medium, OpenRouter fast/ultrafast, model_map의 가짜 extra_body, effort 생략을 모두 제안 검증기에서 거부한다.
- 부정 사례 거부는 오프라인 검증기 동작이며 실제 endpoint에 잘못된 유료 요청을 보낸 결과가 아니다. provider가 옵션을 받아들여도 실제 동작을 무시할 수 있으므로 실호출이 최종 검증이다.
- live config는 무변경이다. Docker에 호스트 hermes CLI가 없으므로 운영 적용·신규 경로 호출은 수행하지 않았다.
- 다음 적용 전: 경로마다 짧은 응답 → 강제 도구 호출 → 도구 결과 반영 → 구조화 출력 → 시각 경로 이미지 판독을 실행한다. 성공 응답의 provider/model/실제 wire 옵션, 비용·reasoning tokens·시간·재시도를 기록한다.
- 같은 모델 Quick/Balanced/Deep을 동일 과제로 비교하여 강도 차이가 실제 소비·품질에 반영되는지 확인한다. none은 enabled=false로 전달되고 fast/speed 키가 요청에 남지 않는지도 확인한다.
- 옵션 변경은 새 세션에서 반영하고 설정 read-back 및 option enum을 확인한다. 대화 중 도구 스키마를 강제로 바꾸지 않는다.[3]

## 산출물 및 적용 범위

- `model-map-proposal.json`: 기존 제안 대체. 실행 후보 경로만 포함, 기본값 M-Haiku-Balanced. 모두 normal·명시적 effort·자동 폴백 없음.
- `variant-specs.json`: 모델별 변형의 역할·금지 조건·목표 속도·wire 변환·가격. 실제 설정 JSON과 구분한다.
- `adapters/hermes/validation/installed-probes.json`: 설치된 Hermes 변환·파서 함수 검사 결과(추론 호출 아님). 이전의 오프라인 규칙 검사는 `tests/`의 단위 테스트로 대체됨(옛 `variant-validation.json`은 git 이력에 있음). 실호출 결과와 혼동하지 말 것.
- `openrouter-models-variants.json`: 최신 공개 모델 목록 원본.
- `variant-extra-endpoints.json`: Kimi Pro·DeepSeek Pro·Gemini Argon·MiMo Pro 정확한 ID endpoint 응답.
- 이전 v1 문서/제안은 작성 환경의 백업 폴더에 보관했으며 이 저장소에는 없다. 현재 제안은 `core/spec/variant-specs.json`(원본)에서 `adapters/hermes/export_model_map.py`로 생성한다. 이전 생성기 `build_variants.py`는 제거되었다.

## 지금 달성한 것 → 다음 단계

모델명 기반 추천을 작업별 변형 체계로 개정·옵션 상속 및 속도 제약 발견·오프라인 검증 완료 → 실호출 예산/범위 확정 후 endpoint·도구 왕복 검증을 통과한 경로만 운영 적용.

## Sources

[1] https://openrouter.ai/api/v1/models
[2] https://openrouter.ai/docs/api_reference/limits
[3] https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
[6] https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
[7] https://openrouter.ai/docs/guides/routing/provider-selection
[8] https://openrouter.ai/api/v1/models/moonshotai/kimi-k3.1-pro/endpoints
[9] https://openrouter.ai/api/v1/models/deepseek/deepseek-v4-pro/endpoints

## 전용 결정 모델(Jev 등)을 이용한 라우팅·필터링 검토

- 상세 설계: `hybrid-routing-design.md` (조사·설계 단계, 실호출·운영 변경 없음).
- 결론: 규칙 코드가 자격·금지 조건을 먼저 확정하고, 결정 모델은 작업 유형·난도·위험을 확률로 추천하며, 저확신·고위험·충돌은 고성능 부모가 결정한다.
- 연결 방식: 호스트 측 플러그인 도구가 현실적이다. 설치된 `model_map`은 provider/model/base_url/api_key/api_mode/reasoning_effort/service_tier(+fallback_providers)만 전달하므로 Jev Router의 `cost_tier`·모델 목록은 서브에이전트 경로에서 쓸 수 없다.
- 정확도·비용 절감은 미측정이다. 그림자 모드로 부모 판단과 비교한 뒤 임계값을 보정한다.
