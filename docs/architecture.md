# 아키텍처: 에이전트 중립 코어 + 어댑터

## 목표

이 저장소는 Hermes 전용 설정집이 아니라, **어떤 에이전트 프레임워크에서도 서브에이전트를 비용 대비 효율로 배정하는 데 쓸 수 있는 정책·데이터·도구**를 지향한다. Hermes는 첫 번째 어댑터이자 검증 환경이다.

## 현재 파일의 결합도 (2026-10-30 점검)

| 구분 | 파일 | 상태 |
|---|---|---|
| 이미 중립 | `data/variant-specs.json`, `data/tier-taxonomy-proposal.json`, `skills/.../templates/task-contract.md`, `data/recommended-costs.json` | Hermes 용어 없음 |
| Hermes 전용 | `data/model-map-proposal.json`, `scripts/build_variants.py` | Hermes `model_map` 형식, 설치된 플러그인 코드를 직접 검사 |
| 혼재 | `skills/subagent-orchestration/SKILL.md`, `references/*`, `docs/*` | 정책 본문에 `delegate_task`, `option` 같은 Hermes 용어가 섞임 |

## 목표 구조

```text
core/                      에이전트 중립 (Hermes 용어 금지)
  spec/                    변형 명세, 티어 분류의 스키마와 데이터
  policy/                  라우팅 정책, 작업 계약, 승격·중단 규칙
  eligibility/             하드 규칙 판정기 (표준 라이브러리만 사용)
  catalog/                 OpenRouter 모델 API에서 후보·가격·지원 옵션을 수집
adapters/
  hermes/                  model_map 내보내기, SKILL.md, 설치된 플러그인 검증
  (후보) 기타 프레임워크   형식을 공식 문서로 확인한 뒤에만 추가
optional/
  decision-model/          Jev 등 결정 모델 추천기 (선택 기능, 기본 꺼짐)
docs/                      설계·근거·검증 기록
```

## 중립 코어의 입출력 계약

- **입력:** 작업 설명 요약, 모달리티, 입력 길이, 쓰기 범위, 위험 신호, 사용 가능한 경로 목록(어댑터가 제공).
- **출력:** 추천 변형 이름, 거부된 후보와 사유, 부모에게 이관할지 여부.
- **원칙:** 코어는 특정 에이전트의 도구 이름이나 설정 형식을 모른다. 경로 목록과 지원 옵션은 어댑터가 주입한다.
- **하드 규칙(자격 판정):** 미등록 경로 금지, 지원하지 않는 추론·속도 값 금지, 모달리티·길이 한도, 쓰기 충돌, 무료→유료 자동 전환 금지. 신경망 추천으로 우회하지 못한다.

## 어댑터 원칙

1. 어댑터는 중립 명세를 대상 형식으로 **변환**하고 대상 환경에서 **검증**한다. 정책을 새로 정하지 않는다.
2. 대상 형식은 공식 문서나 실제 설치본으로 확인한 뒤에만 지원한다고 적는다. 확인 전에는 "후보"로 표기한다.
3. 각 어댑터는 지원하지 못하는 항목을 명시한다. (예: Hermes `model_map`은 provider·model·base_url·api_key·api_mode·reasoning_effort·service_tier·fallback_providers만 전달)

## 이전 작업 순서

1. 중립 파일과 Hermes 전용 파일을 분리해 이동한다. (`git mv`로 이력 유지)
2. `SKILL.md`에서 정책 본문을 `core/policy/`로 추출하고, `SKILL.md`는 Hermes 용어로 정책을 가리키는 얇은 어댑터로 줄인다.
3. `build_variants.py`를 `catalog`(중립 수집)와 `adapters/hermes`(내보내기·검증)로 나눈다. 절대 경로는 인자와 환경변수로 바꾼다.
4. 하드 규칙 판정기를 코드로 구현하고 단위 테스트를 작성한다. (현재 이 저장소에는 테스트가 없다)
5. 두 번째 어댑터 후보를 하나 골라 형식을 확인하고, 중립성이 실제로 성립하는지 검증한다.

## 범용성 판단 기준 (완료 정의)

- `core/`에 `hermes`, `delegate_task`, `model_map` 문자열이 없다(자동 검사).
- Hermes 없이 코어 판정기 테스트가 통과한다.
- 어댑터를 하나 더 붙였을 때 코어 수정이 필요 없다.
- 위 세 항목이 확인되기 전에는 README에 "범용"이라고 쓰지 않는다.

## 위험과 미결정

- 모델 이름·가격·지원 옵션은 빠르게 변한다. 데이터에는 수집 날짜와 출처를 붙이고 오래된 값을 쓰지 않도록 한다.
- 변형별 역할은 측정 전 가설이다. 다른 프레임워크에서는 도구 호출 방식과 옵션 지원이 달라 같은 변형이 같은 성능을 낸다고 보장할 수 없다.
- 저장소 이름: 현재 `hermes-subagent-routing-kit`은 범용 목표와 맞지 않는다. 후보는 `subagent-routing-kit`이다. 로컬 폴더명을 바꾸면 Hermes 프로젝트 경로가 어긋나므로 이름이 확정된 뒤 프로젝트를 다시 연결해야 한다.

## 진행 기록

- 2026-10-30: 저장소 이름을 `subagent-routing-kit`으로 확정, Apache-2.0 `LICENSE` 원문 추가(공식 원문과 크기·줄 수 일치 확인).
- 2026-10-30: 이전 작업 순서 1~3 완료. 중립 파일과 Hermes 전용 파일 분리(`git mv`), 정책 본문을 `core/policy/`로 추출, 스킬은 얇은 어댑터로 축소(`sync_skill.py`로 사본 동기화), `core/catalog/inspect_endpoints.py`를 CLI로 일반화.
- 2026-10-30: 순서 4 완료. `core/eligibility`(하드 규칙 판정기)와 `core/catalog/build_capabilities.py`(모델 능력 수집) 구현, 단위 테스트 63개 통과. 규칙을 일부러 망가뜨린 변형 7개를 모두 검출함. 구현 중 쓰기 범위가 저장소 전체(`.`)인 작업이 충돌로 판정되지 않던 결함을 발견해 수정함.
- 2026-10-30: 순서 3 완료. `build_variants.py`(데이터 정의·규칙 검증·내보내기·설치본 검사·문서 생성이 한 파일)를 분리함. 데이터 원본은 `core/spec/variant-specs.json`, 내보내기는 `adapters/hermes/export_model_map.py`(core 판정기 사용), 설치본 검사는 `adapters/hermes/validate_installed.py`. 기존 `model-map-proposal.json`을 바이트 단위로 재현하는 것을 합격 기준으로 삼아 통과함. 계획 문서 자동 생성은 제거(수동 관리). 단위 테스트 76개.
- 남은 작업: 순서 5(두 번째 어댑터 검증). 이것이 끝나기 전에는 "범용"이라고 주장하지 않는다.
