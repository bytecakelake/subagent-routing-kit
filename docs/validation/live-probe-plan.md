# 실호출 프로브 계획 — 17경로 검증 (2026-10-30)

## 목적

`model_map` 17경로가 실제로 **호출되고, 도구를 쓰고, 형식을 지키는지** 확인합니다. 지금까지 확인한 것은 설정 반영과 오프라인 호환성뿐이며, 이것은 성능·품질 측정이 아닙니다.

## 범위와 예산

- 대표 5경로 + 기본 경로 1개(이미 스모크 완료) = 6경로. 17경로 전수는 이 단계가 통과한 뒤로 미룹니다.
- 상한: 전체 **$1**, 프론티어 경로는 각 1회, 경로별 연속 실패 2회면 그 경로는 중단.
- 병렬은 배치 2개까지. `max_concurrent_children` 이 30이므로 명시적으로 낮춰 씁니다.

## 대상 경로

| 경로 | 모델 | 추론 | 확인하는 것 |
|---|---|---|---|
| `M-Haiku-Balanced` (기본) | claude-haiku-5.5 | medium | 기본 경로가 option 없이도 도는지 (스모크) |
| `F-Sol-Deep` | gpt-6.1-sol | high | 프론티어·high 강도가 실제로 수용되는지 |
| `M-Terra-Balanced` | gpt-6.1-terra | medium | 미들 기본 경로 |
| `L-GLM-Extract` | glm-5.3-flash | low | 추론 필수 모델 + low 조합 |
| `Free-Nemotron-Visual` | nemotron-3.5-super-vl:free | none | 무료 경로 + `none`(추론 끄기) 전달 |
| `MM-Gemini-Inspect` | gemini-4-argon | low | 시각 입력 판독 |

## 프로브 3단계

각 경로에 같은 순서로 적용합니다. 앞 단계가 실패하면 뒤 단계는 건너뜁니다.

1. **짧은 응답** — 도구를 쓰지 말고 정확히 `PROBE-OK` 만 반환. 경로 자체가 응답하는지.
2. **강제 도구 호출** — `README.md` 첫 제목 줄을 읽어 그대로 보고. 도구 왕복이 실제로 되는지.
3. **구조화 출력** — `{"route": "<이름>", "read_ok": true, "first_heading": "<문자열>"}` 형태의 JSON 만 반환. 형식 준수.

시각 경로(`MM-Gemini-Inspect`)는 1·2단계 대신 **이미지 1장 판독**으로 대체합니다. 이미지는 저장소 안의 기존 이미지나 간단한 차트 1장을 씁니다.

## 기록 형식

`docs/validation/live-probes-20261030.json` 에 경로별로 남깁니다.

```json
{
  "route": "F-Sol-Deep",
  "model": "openai/gpt-6.1-sol",
  "reasoning_effort": "high",
  "probes": [
    {"step": "short", "ok": true, "reply": "PROBE-OK", "error": null},
    {"step": "tool", "ok": true, "reply": "…", "error": null},
    {"step": "json", "ok": true, "reply": "{…}", "error": null}
  ],
  "observed": "자식 응답에서 확인한 사실만. 모델·지연·비용은 확정 수치가 아니면 추정이라고 표시"
}
```

지연·비용은 자식이 돌려주지 않으면 **측정하지 않았다**고 적습니다. 추정치를 실측처럼 쓰지 않습니다.

## 판정 기준

| 결과 | 해석 |
|---|---|
| 3단계 모두 통과 | 그 경로는 도구 작업에 사용 가능 |
| 1단계만 통과 | 텍스트 전용 작업에만 사용. 도구 작업 배정 금지 |
| 2단계 실패(도구 미호출/오류) | 경로 자체를 사용 금지하고 원인 기록 |
| 옵션 거부·오류 응답 | 설정 문제이므로 경로를 빼고 재검토 |
| 무료 경로 실패 | 유료로 자동 승격하지 않고 실패로 기록 |

## 중단 조건

- 같은 경로에서 연속 2회 실패 → 그 경로 중단, 나머지 계속
- 예산 상한 접근 → 남은 경로 보류하고 보고
- 게이트웨이나 설정이 바뀌면 → 세션 스키마가 달라지므로 재시작 후 다시 시작

## 실행 결과 (2026-10-30)

원자료는 `docs/validation/live-probes-20261030.json` 입니다. 경로별 모델은 각 delegation 의 `manifest.json` 으로 교차 확인했습니다.

| 경로 | 실제 모델 | 프로브 | 판정 |
|---|---|---|---|
| `F-Sol-Standard` | gpt-6.1-sol | 도구+JSON | 통과 |
| `F-Sol-Deep` | gpt-6.1-sol | 응답·도구·JSON | 3단계 통과 |
| `F-Sonnet-Code` | claude-sonnet-5.5 | 도구+JSON | 통과 |
| `F-Sonnet-Debug` | claude-sonnet-5.5 | 도구+JSON | 통과 |
| `M-Terra-Quick` | gpt-6.1-terra | 도구+JSON | 통과 |
| `M-Terra-Balanced` | gpt-6.1-terra | 응답·도구·JSON | 3단계 통과 |
| `M-Terra-Deep` | gpt-6.1-terra | 도구+JSON | 통과 |
| `M-DeepSeekPro-Plain` | deepseek-v4-pro | 도구+JSON | 통과(추론 끔) |
| `M-DeepSeekPro-Reason` | deepseek-v4-pro | 도구+JSON | 값 통과·**코드펜스** |
| `M-Haiku-Quick` | claude-haiku-5.5 | 도구+JSON | 통과 |
| `M-Haiku-Balanced` | claude-haiku-5.5 | 응답 | 통과 |
| `M-Qwen-Lite` | qwen3.8-flash | 도구+JSON | 통과(추론 끔) |
| `L-GLM-Extract` | glm-5.3-flash | 응답·도구·JSON | 3단계 통과 |
| `Free-Nemotron-Visual` | nemotron-3.5-super-vl:free | 응답·도구·이미지 | 조건부 통과 |
| `MM-MiMo-Inspect` | mimo-v2.6-flash | 이미지 | 값 통과·**키 불일치** |
| `MM-Gemini-Inspect` | gemini-4-argon | 이미지 | 판독 정확 |
| `MM-Gemini-Reason` | gemini-4-argon | 이미지(추론) | 최대·최소·차이 70 정확 |

17경로 모두 기능적으로 응답했고, 도구가 필요한 경로는 실제로 도구를 실행했습니다. 실패는 없었지만 **형식 편차 두 건**이 나왔습니다.

- `M-DeepSeekPro-Reason` 은 JSON 을 ```json 코드펜스로 감쌌습니다. 값은 정확하므로 소비자가 펜스를 벗기는 후처리를 넣어야 합니다.
- `MM-MiMo-Inspect` 는 키를 `route` 가 아니라 `route set` 으로 합쳐 반환했습니다. 값은 맞지만 스키마를 그대로 신뢰하면 파싱이 깨집니다.

**주의해서 볼 결과 하나.** 무료 경로에 `echo TOOL-OK` 를 시키자 도구를 실행하지 않고 응답만 `TOOL-OK` 로 지어냈습니다(transcript 에 tool 단계 없음, `api_calls=1`). 추측할 수 없는 값(`md5sum` 앞 12자)으로 다시 시키자 실제로 실행해 정확한 값을 반환했습니다. 즉 무료 경로는 **결과를 예측할 수 있는 명령에서 도구를 건너뛸 수 있으므로**, 배정 시 "실행하지 않으면 실패로 간주한다" 같은 강제 조건을 계약에 넣어야 합니다. 이는 이 경로만의 문제가 아니라 작은 모델 전반의 위험이므로, 자식 결과를 받을 때 도구 흔적을 함께 확인하는 편이 안전합니다.

**아직 확인하지 않은 것:** 품질(같은 과제를 Quick/Balanced/Deep 으로 비교), 실제 비용(`usage.cost`), 지연 분포, 도구 왕복이 여러 번 필요한 다단계 작업, 이미지 2장 이상 동시 입력, 경로별 반복 실행의 분산.

## 실사용 기록

프로브는 "경로가 작동한다"까지만 증명합니다. 어떤 경로가 실제로 값을 하는지는 실사용 기록으로 판단합니다. `docs/validation/usage-log.csv` 에 한 줄씩 남기십시오.

| 열 | 넣을 값 |
|---|---|
| `date` | 2026-10-30 형식 |
| `route` | `delegate_task` 에 넘긴 option 이름 |
| `model` | 자식이 실제로 쓴 모델. `%LOCALAPPDATA%\hermes\cache\delegation\live\<delegation_id>\manifest.json` 의 `model` 값 |
| `task_type` | 추출·요약·구현·디버깅·시각 판독 같은 짧은 분류 |
| `outcome` | `ok` / `partial` / `fail` |
| `escalated_to` | 승격했다면 올린 경로, 아니면 비움 |
| `tool_evidence` | 자식이 실제로 도구를 실행했는지 `y`/`n` (transcript 의 tool 단계 확인) |
| `cost_usd` | 실제 청구액을 확인했을 때만. 모르면 비움 — 추정치를 적지 않음 |
| `minutes` | 체감 소요. 정밀 측정이 아니면 대략값 |
| `note` | 실패 원인, 형식 편차, 다시 쓸지 여부 |

최소한 `date`·`route`·`task_type`·`outcome` 네 개만 채워도 승격률과 경로별 실패 유형이 보입니다. 30건쯤 모이면 경로별 성공률과 승격 사유를 표로 만들 수 있고, 그때 임계값과 기본 경로를 조정합니다.

## 산출물

1. `docs/validation/live-probes-20261030.json` — 원자료
2. 이 문서 아래에 경로별 요약 표 추가
3. 통과 경로만 `core/policy/routing-policy.md` 의 배정 예시에 반영할지 별도 판단
