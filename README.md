# subagent-routing-kit

서브에이전트를 **비용 대비 효율**로 배정하기 위한 정책, 데이터, 도구 모음입니다. 모델을 티어와 작업별 변형(모델 + 추론 강도 + 속도)으로 나누고, 위임 방법을 정책 문서로 정리했습니다. 정책과 데이터는 에이전트 중립 `core/`에 두고, 각 에이전트 프레임워크용 변환과 검증은 `adapters/`에 둡니다. 첫 어댑터는 Hermes입니다.

라이선스: Apache-2.0 (`LICENSE`)

## 상태: v0.2 (구조 분리 직후)

| 구분 | 상태 |
|---|---|
| 티어 분류(F1~V2)와 17개 변형 명세 | 설계 완료. **어떤 운영 환경에도 미적용** |
| 중립 정책(`core/policy`) | 작성 완료. `tools/check_core_neutral.py`로 종속 용어 없음을 검사 |
| Hermes 어댑터 | 얇은 스킬 + 동기화 스크립트 완료. 변형 생성기(`build_variants.py`)는 이전한 그대로이며 **절대 경로에 의존** |
| 신규 17개 경로의 실호출 검증 | **미실시** (옵션 호환, 도구 왕복, 품질, 비용, 지연) |
| 전용 결정 모델(Jev 등) 하이브리드 라우팅 | 설계만 있음. 정확도와 절감 효과는 **미측정** |
| 하드 규칙 판정기, 단위 테스트 | **미구현** |
| 두 번째 어댑터 | **없음**. 그러므로 중립성은 아직 한 환경에서만 확인된 상태 |

역할 배정은 운영 가설이며 측정된 성능 순위가 아닙니다. 모델 가격과 외부 평가 지표는 2026-10-30 시점의 OpenRouter 공개 메타데이터이며 변경될 수 있습니다.

## 구성

```text
core/                         에이전트 중립 (종속 용어 금지, 자동 검사)
  spec/                       변형 명세, 티어 분류, 비용 데이터
  policy/                     운영 정책, 라우팅 정책, 작업 계약 양식
  catalog/                    OpenRouter 엔드포인트 조회 도구
adapters/
  hermes/                     Hermes용 스킬, model_map 제안, 동기화 스크립트, 변형 생성기
docs/                         설계, 조사 근거, 검증 기록
tools/                        저장소 검사 스크립트
```

설계의 배경과 완료 조건은 `docs/architecture.md`를 보십시오.

## 사용

모두 Python 3 표준 라이브러리만 사용합니다.

```bash
# 모델 엔드포인트(가격, 지원 파라미터) 조회. 인증 키 불필요
python core/catalog/inspect_endpoints.py --from-specs core/spec/variant-specs.json --out endpoints.json

# core/ 에 특정 에이전트 종속 용어가 없는지 검사
python tools/check_core_neutral.py

# Hermes 스킬 사본을 core/policy 와 맞추기 / 일치 여부만 검사
python adapters/hermes/sync_skill.py
python adapters/hermes/sync_skill.py --check
```

Hermes에서는 `adapters/hermes/skill/subagent-orchestration/`을 스킬 폴더에 설치합니다. 설치된 사본은 저장소와 자동으로 동기화되지 않습니다.

## 핵심 원칙

- 티어는 모델의 격이 아니라 **운영 정책**입니다. 특정 모델군을 일괄 배제하지 않고 작업 난이도 대비 가치로 판단합니다.
- 모든 경로에 추론 강도와 속도를 **명시**합니다. 생략하면 부모 설정을 상속합니다. 지원이 확인되지 않은 옵션은 쓰지 않습니다.
- 무료→유료 자동 전환, 미등록 경로 호출, 비슷한 이름으로의 조용한 대체를 하지 않습니다.
- 규칙 코드가 자격·금지 조건을 먼저 확정하고, 결정 모델은 추천만 하며, 애매하거나 위험한 건은 고성능 부모가 결정합니다.

## 알려진 한계

- `adapters/hermes/build_variants.py`는 작성 환경의 경로(`/workspace/...`, `/hermes-home/...`)와 설치된 Hermes 플러그인 코드를 직접 읽습니다. 다른 환경에서는 실행되지 않습니다. 중립 수집부와 Hermes 내보내기로 나누는 작업이 남아 있습니다.
- 가격 스냅샷(`openrouter-models*.json`, 각 1.2MB)은 저장소에 포함하지 않았습니다. 필요하면 OpenRouter 모델 API에서 다시 받으십시오.
- `core/spec/`의 가격과 지원 옵션은 수집 시점의 값입니다. 사용 전에 다시 확인하십시오.
- 설치된 `advanced-delegation` 플러그인의 `model_map`은 provider, model, base_url, api_key, api_mode, reasoning_effort, service_tier, fallback_providers만 전달합니다. 그 밖의 라우터 옵션은 서브에이전트 경로에서 쓸 수 없다고 가정합니다.
- `docs/` 안의 일부 문서는 이전 경로(`/workspace/docs/subagent-rebuild/...`)를 언급합니다. 정리 전입니다.
