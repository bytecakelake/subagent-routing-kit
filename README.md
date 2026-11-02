# subagent-routing-kit

서브에이전트를 **비용 대비 효율**로 배정하기 위한 정책, 데이터, 도구 모음입니다. 모델을 티어와 작업별 변형(모델 + 추론 강도 + 속도)으로 나누고, 위임 방법을 정책 문서로 정리했습니다. 정책과 데이터는 에이전트 중립 `core/`에 두고, 각 에이전트 프레임워크용 변환과 검증은 `adapters/`에 둡니다. 첫 어댑터는 Hermes입니다.

라이선스: Apache-2.0 (`LICENSE`)

## 상태: v0.4 (Hermes 어댑터가 core 판정기를 사용)

| 구분 | 상태 |
|---|---|
| 티어 분류(F1~V2)와 23개 변형 명세 | 설계 완료. 저장소 명세·제안 파일은 23경로(고성능 F1/F2 에 오픈웨이트 6경로 추가: GLM 5.3·DeepSeek V4 Pro 0813·Qwen3.8 2.4T). default 프로필의 `model_map` 에는 **아직 17경로만** 적용됨(기본 `M-Haiku-Balanced`). 23경로 적용은 아래 절차 필요. 다른 프로필은 미적용 |
| 중립 정책(`core/policy`) | 작성 완료. `tools/check_core_neutral.py`로 종속 용어 없음을 검사 |
| Hermes 어댑터 | 얇은 스킬, `model_map` 내보내기(core 판정기 사용), 설치된 Hermes 검사 완료. 설치본 검사 9개 통과(추론 호출 아님) |
| 경로의 실호출 검증 | 기존 17경로 전수 통과(오픈웨이트 6경로는 **미검증**, 적용 후 실호출 필요)(응답·도구 왕복·구조화 출력·시각 판독). 형식 편차 2건은 `docs/validation/live-probe-plan.md` 에 기록. 근거 `docs/validation/live-probes-20261030.json`. 품질·비용·지연은 **미측정** |
| 전용 결정 모델(Jev 등) 하이브리드 라우팅 | 설계만 있음. 정확도와 절감 효과는 **미측정** |
| 하드 규칙 판정기 (`core/eligibility`) | 구현 완료. **런타임 연결 플러그인** `adapters/hermes/plugin/routing-guard` 가 `delegate_task` 실행 전에 위반 경로를 차단. 테스트 112개 통과(판정기·가드·내보내기 포함) |
| 두 번째 어댑터 | **없음**. 그러므로 중립성은 아직 한 환경에서만 확인된 상태 |

역할 배정은 운영 가설이며 측정된 성능 순위가 아닙니다. 모델 가격과 외부 평가 지표는 2026-10-30 시점의 OpenRouter 공개 메타데이터이며 변경될 수 있습니다.

## 구성

```text
core/                         에이전트 중립 (종속 용어 금지, 자동 검사)
  spec/                       변형 명세, 티어 분류, 비용 데이터, 출력 계약 스키마(output-contract.schema.json)
  policy/                     운영 정책, 라우팅 정책, 작업 계약 양식
  catalog/                    OpenRouter 엔드포인트 조회, 모델 능력 수집
  eligibility/                하드 규칙 판정기 (경로 자격, 쓰기 범위 충돌)
  contract/                   자식 보고(JSON)의 검증기 (pydantic, strict). 원본 계약은 spec/output-contract.schema.json
  jsonio.py                   JSON 읽기·쓰기 래퍼 (orjson). 표준 json 과의 차이를 한 곳에서 관리
adapters/
  hermes/                     Hermes용 스킬, model_map 내보내기·검사, 스킬 동기화
docs/                         설계, 조사 근거, 검증 기록
tests/                        단위 테스트 (unittest)
tools/                        저장소 검사 스크립트
```

설계의 배경과 완료 조건은 `docs/architecture.md`를 보십시오.

## 사용

Python 3.13 에서 검증했습니다. 실행에는 `orjson`, `httpx`, `pydantic`이 필요합니다. 판정기(`core/eligibility`), 플러그인, 정책 동기화·검사 스크립트는 표준 라이브러리만 쓰므로 Hermes 안에서는 추가 설치가 필요 없습니다.

```bash
# 설치 (개발·테스트까지 하려면 requirements-dev.txt)
pip install -r requirements.txt

# 모델 엔드포인트(가격, 지원 파라미터) 조회. 인증 키 불필요
python core/catalog/inspect_endpoints.py --from-specs core/spec/variant-specs.json --out endpoints.json

# 단위 테스트 (pytest 불필요, unittest). requirements-dev.txt 의 jsonschema 가 있으면 계약 검증기와 스키마의 판정 일치도 검사
python -m unittest discover -s tests -t .

# 모델 능력 다시 수집 (공개 API). 수집 후 테스트로 명세와의 일치를 확인
python core/catalog/build_capabilities.py --specs core/spec/variant-specs.json --out core/spec/model-capabilities.json

# Hermes: 명세에서 model_map 제안 만들기 / 최신인지 검사 / 설치된 Hermes 가 제안을 의도대로 읽는지 검사
python adapters/hermes/export_model_map.py
python adapters/hermes/export_model_map.py --check
python adapters/hermes/validate_installed.py --hermes-home <HERMES_HOME 경로>

# model_map 적용: 검증만 / config.yaml 에 들어갈 블록 확인 / 백업 후 실제 적용 / 적용+재시작
python adapters/hermes/apply_model_map.py
python adapters/hermes/apply_model_map.py --print-yaml
python adapters/hermes/apply_model_map.py --apply
python adapters/hermes/apply_model_map.py --apply --restart

# core/ 에 특정 에이전트 종속 용어가 없는지 검사
python tools/check_core_neutral.py

# Hermes 스킬 사본을 core/policy 와 맞추기 / 일치 여부만 검사
python adapters/hermes/sync_skill.py
python adapters/hermes/sync_skill.py --check

# routing-guard 플러그인의 판정기·능력 사본을 core 와 맞추기 / 일치 여부만 검사
python adapters/hermes/sync_plugin.py
python adapters/hermes/sync_plugin.py --check
```

Hermes에서는 `adapters/hermes/skill/subagent-orchestration/`을 스킬 폴더에 설치합니다. 설치된 사본은 저장소와 자동으로 동기화되지 않습니다.

## 하드 규칙 판정기

`core/eligibility`는 경로가 자격을 갖췄는지 코드로 판정합니다. 부모 판단이나 결정 모델 추천으로 우회할 수 없습니다.

| 규칙 | 거부 조건 |
|---|---|
| 등록 | 어댑터가 알려 준 등록 경로 목록에 없음 |
| 추론 강도 | 명시하지 않음, 모델이 공개한 목록에 없음, 목록이 비공개인 모델에 강도 지정, 추론 필수 모델 또는 추론 미지원 모델에 `none` |
| 속도 | 명시하지 않음, 검증된 단계(`normal`) 밖 |
| 무료→유료 | 무료 경로의 폴백이 유료이거나 알 수 없음 |
| 입력 | 필요한 모달리티·도구 미지원, 컨텍스트 초과, 장문 할증 구간(명시적 허용 시 통과) |

입력 길이를 모르면 거부하지 않고 경고합니다. 위험 신호(`high_risk`)는 독립 검토 플래그를 **추가**할 뿐 어떤 규칙도 풀지 않으며, 승인이 필요한 작업은 후보가 있어도 `needs_approval`입니다. 후보를 거르는 데까지가 이 모듈의 몫이고, 남은 후보 중 선택과 모호한 건의 처리는 부모의 몫입니다.

```python
from core.eligibility import Task, evaluate, load_capabilities, routes_from_specs
caps = load_capabilities("core/spec/model-capabilities.json")
routes = routes_from_specs("core/spec/variant-specs.json")
d = evaluate(Task("t1", input_tokens=150_000), routes, caps, registered=[r.name for r in routes])
d.status, d.eligible, d.rejected   # 상태, 통과 경로, 경로별 거부 사유
```

쓰기 범위가 겹치는 작업은 `plan_write_stages`로 단계를 나눕니다. 저장소 전체(`.`)를 쓰는 작업은 다른 모든 쓰기 작업과 충돌로 취급합니다.

## model_map 적용

`adapters/hermes/model-map-proposal.json`(23경로)을 설치된 Hermes 의 `delegation.backends.model_map` 에 넣는 순서입니다. `apply_model_map.py` 는 제안 파일을 먼저 검증하고, `config.yaml` 을 백업한 뒤 `hermes config set` 을 두 번(경로 목록, 기본 backend) 실행하고, 마지막에 설정을 다시 읽어 확인합니다. 표준 라이브러리만 쓰며 `--apply` 없이는 아무것도 바꾸지 않습니다.

1. `python adapters/hermes/export_model_map.py --check` — 제안 파일이 명세와 일치하는지 확인
2. `python adapters/hermes/apply_model_map.py` — 23경로·기본값·이름 규칙·추론 강도 검사(쓰기 없음)
3. `python adapters/hermes/apply_model_map.py --apply` — 백업 후 적용, read-back 확인까지
4. `--apply --restart` 를 붙이면 재시작까지 한 번에 처리합니다(진행 중인 대화·cron·백그라운드 위임이 끊기므로 y/N 확인을 받습니다). 따로 할 때는 `hermes gateway restart -y` 를 실행하고, **새 세션**에서 `delegate_task` 의 `option` 목록에 23개 이름이 보이는지 확인하십시오.

설정은 프로필 단위이므로 다른 프로필에 넣을 때는 `-p <프로필>` 을 붙입니다. 되돌릴 때는 스크립트가 출력한 백업 파일을 `config.yaml` 로 복사하고 다시 재시작합니다. 기존 17경로의 실호출 검증 결과는 `docs/validation/live-probe-plan.md` 에 있습니다.

## 런타임 판정기 (routing-guard)

`core/eligibility` 판정기를 Hermes 실행 경로에 연결한 플러그인입니다. `delegate_task` 의 `pre_tool_call` 훅에서 호출을 가로채, 선택된 `model_map` 경로가 하드 규칙(등록 여부·추론 강도·속도·무료→유료 폴백·모달리티·도구·컨텍스트)을 통과하는지 확인하고 위반이면 `{"action": "block"}` 으로 실행을 막습니다. 차단 메시지에는 위반 코드와 대안 경로가 함께 나갑니다.

```bash
python adapters/hermes/sync_plugin.py --check   # 플러그인의 판정기·능력 사본이 core 와 같은지
```

설치·설정·한계는 `adapters/hermes/plugin/routing-guard/README.md` 에 있습니다. 요약하면 플러그인 폴더를 `%LOCALAPPDATA%\hermes\plugins\` 로 복사하고 `plugins.enabled` 에 `routing-guard` 를 추가한 뒤 게이트웨이를 재시작합니다. 입력 토큰 수·승인 필요 여부·쓰기 범위는 `delegate_task` 인자에 없어 런타임에서 강제되지 않습니다.

## 핵심 원칙

- 티어는 모델의 격이 아니라 **운영 정책**입니다. 특정 모델군을 일괄 배제하지 않고 작업 난이도 대비 가치로 판단합니다.
- 모든 경로에 추론 강도와 속도를 **명시**합니다. 생략하면 부모 설정을 상속합니다. 지원이 확인되지 않은 옵션은 쓰지 않습니다.
- 무료→유료 자동 전환, 미등록 경로 호출, 비슷한 이름으로의 조용한 대체를 하지 않습니다.
- 규칙 코드가 자격·금지 조건을 먼저 확정하고, 결정 모델은 추천만 하며, 애매하거나 위험한 건은 고성능 부모가 결정합니다.
- 비용은 부모가 아니라 자식에서 줄입니다. 부모를 Sonnet·Terra급으로 낮춰 전담시키자 품질이 떨어졌다는 현장 피드백(2026-11-01)에 따라, 부모 하향은 같은 과제로 비교하고 즉시 되돌릴 수 있는 실험으로만 합니다.
- 사용자 승인은 검증이 아닙니다. 사용자에게는 지출·게시·삭제·범위 같은 권한 결정만 묻고, 기술적 정확성은 테스트·근거·전문 검토로 먼저 확정한 뒤 쉬운 말로 바로 결정할 수 있는 요청을 올립니다.

## 알려진 한계

- `core/spec/variant-specs.json`이 변형의 **원본**입니다(역할·금지 조건·가격은 손으로 관리). 이전에 이 파일을 생성하던 `build_variants.py`와 계획 문서 자동 생성은 제거했습니다(git 이력에 남아 있음). `docs/openrouter-subagent-rebuild-plan.md`는 이제 수동 관리 문서이고 일부 수치는 작성 시점 기준입니다.
- 변형 명세의 가격(`input_per_million` 등)은 2026-10-30 값이며 자동으로 갱신되지 않습니다. 모델 능력(`model-capabilities.json`)만 수집 스크립트로 갱신됩니다.
- `core/spec/`의 가격과 지원 옵션은 수집 시점의 값입니다. 사용 전에 다시 확인하십시오.
- 설치된 `advanced-delegation` 플러그인의 `model_map`은 provider, model, base_url, api_key, api_mode, reasoning_effort, service_tier, fallback_providers만 전달합니다. 그 밖의 라우터 옵션은 서브에이전트 경로에서 쓸 수 없다고 가정합니다.
- 판정기가 쓰는 모델 능력(`model-capabilities.json`)은 수집 시점(2026-10-30)의 공개 메타데이터입니다. 모델·가격·지원 옵션은 바뀌므로 사용 전에 다시 수집하십시오.
- `validate_installed.py`는 설치된 Hermes 소스의 변환·파서 함수를 실행하는 검사입니다. 설치 버전이 바뀌면 다시 실행해야 하며, 통과가 실제 호출 성공을 뜻하지는 않습니다.
