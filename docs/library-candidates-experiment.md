# 라이브러리 후보 실험 기록

브랜치: `experiment/library-candidates`. 표준 라이브러리 구현을 후보 라이브러리와 비교한 측정 기록입니다. `main`에는 후보를 도입하지 않았고, 이 브랜치의 `core/`는 스키마 캐시 수정 외에는 바뀌지 않았습니다.

## 측정 방법

- 환경: 도커 샌드박스(WSL2), Python 3.13.16, 저장소 밖 격리 venv(`/workspace/.envs/rk-exp`). 저장소 파일은 호스트 마운트 위에 있어 파일 I/O가 느립니다.
- 스크립트: `bench/bench_candidates.py`, 원자료: `bench/results.json`. 재실행: `<venv>/bin/python bench/bench_candidates.py`.
- 설치 버전: orjson 3.13.0, jsonschema 4.26.0, fastjsonschema 2.22.3, httpx 0.28.1, pydantic 2.14.2, pytest 9.2.0, typer 0.27.3.
- 마이크로 벤치는 7회 반복의 중앙값입니다. 같은 스크립트를 두 번 돌려 결과가 일치함을 확인했습니다.
- 네트워크는 OpenRouter 공개 엔드포인트 13건이며 라운드 3회입니다. 변동이 큽니다.

## 결과

| 영역 | 표준 라이브러리 | 후보 | 비고 |
|---|---|---|---|
| JSON 로드, 명세 4파일 24.8KB | `json` 151µs | `orjson` 55µs | 2.7배 빠르지만 절대값은 0.1ms |
| JSON 로드, 모델 목록 805KB | `json` 8.3ms | `orjson` 3.8ms | 2.2배 |
| 출력 계약 검증, 24건 | 자체 검증기 361µs | `fastjsonschema` 222µs, `jsonschema` 1227µs | 판정은 세 구현이 24건 모두 일치 |
| 데이터 모델 생성 | `dataclass` 1.62µs | `pydantic` 1.49µs | 차이 없음 |
| HTTP 13건 | `urllib` + 스레드 0.18s | `httpx` 동기 0.11s, 비동기 0.22s | 변동 범위 안, 유의미한 차이 없음 |
| 테스트 130개 | `unittest` 1.45s | `pytest` 4.09s | pytest 자체 보고는 1.14s, 나머지는 기동 비용 |
| import 비용 | stdlib 묶음 95ms(기본 기동 약 35ms 포함) | orjson 78ms, fastjsonschema 123~159ms, pydantic 375ms, jsonschema 620ms, httpx 540ms, typer 557ms | 기동 비용은 CLI 단발 실행에서 지연으로 나타남 |

## 해석

- 속도 이득은 `orjson`(JSON)과 `fastjsonschema`(검증)에서만 확인되었으나 절대 시간이 마이크로초~밀리초 단위라, 저장소의 실제 사용(CLI 단발 실행, 25KB 데이터)에서는 체감되지 않습니다.
- `jsonschema`는 자체 검증기보다 3.4배 느리고 import가 620ms로 가장 무겁습니다. 장점은 속도가 아니라 JSON Schema 전체 문법 지원입니다.
- 기대와 달리 `pydantic`과 `httpx`의 처리 속도 이득은 없었고 import 비용만 늘었습니다.
- 실제 병목은 라이브러리가 아니라 `validate()`가 기본 스키마를 호출마다 디스크에서 읽던 것(약 5ms)이었고, 이 브랜치에서 캐시로 고쳤습니다(`core/contract`).
- 측정으로 직접 확인하지 못한 항목: `pytest`, `typer`의 기능상 이점(픽스처, 병렬, 선언적 CLI), `httpx`의 재시도·HTTP/2, `pydantic`의 입력 검증 편의. 속도 외의 가치는 이 실험의 범위 밖입니다.

## 판정 기준 (main 도입 시)

1. 선택 의존성으로만 도입하고, 없으면 표준 라이브러리 경로로 폴백합니다. `core/`는 단독 실행성을 유지합니다.
2. 어댑터가 Hermes 설치본 안에서 로드되므로, 어댑터에는 외부 패키지를 요구하지 않습니다.
3. 계약 검증기는 어떤 구현으로 바꿔도 `tests/test_output_contract.py`와 `bench`의 24건 일치 검사를 통과해야 합니다.

## 속도 외 기준 검증 (`bench/eval_criteria.py`, 원자료 `bench/criteria-results.json`)

### orjson: 같은 결과를 내는가

- `orjson.dumps(..., OPT_INDENT_2) + "\n"`은 저장소의 JSON 6개 모두에서 `json.dumps(indent=2, ensure_ascii=False)`와 바이트 단위로 같았습니다. 한글도 동일합니다.
- 다만 `output-contract.schema.json`과 `recommended-costs.json`은 손으로 정리한 서식이라 어떤 덤퍼로 다시 써도 바뀝니다. 두 파일은 덤프로 재생성하면 안 됩니다.
- 의미가 다른 경우: 64비트를 넘는 정수 쓰기는 오류, 읽기는 **예외 없이 float로 바뀌어 정밀도를 잃음**(`123456789012345678901234567890` → `1.2345678901234568e+29`), `NaN`은 `null`로 쓰고 `[NaN]`은 읽기 오류, 정수 키는 오류, 단독 서로게이트는 오류입니다. `dumps`는 `bytes`를 반환합니다.
- 이 저장소의 데이터에서는 위 경우가 나오지 않았습니다. 큰 정수가 들어오는 입력에는 위험합니다.

### 스키마 검증 라이브러리: 문법 범위와 오류 메시지

- 판정 일치: 24건 모두 일치(앞 절).
- 자체 검증기는 `pattern`, `format`, `$ref`, `oneOf`, `uniqueItems`, `maximum`, `dependentRequired`를 만나면 예외를 던집니다. `jsonschema`는 7개 모두 올바르게 처리했습니다. `fastjsonschema`는 6개를 처리했고 **`dependentRequired`는 오류 없이 무시해서 잘못된 입력을 통과시켰습니다**. 이 라이브러리는 draft-04/06/07까지 지원하므로 2020-12 전용 키워드를 조용히 무시합니다.
- 오류 메시지: 자체 검증기는 한국어이고 필드 경로(`$.evidence[0].path_or_url`)를 줍니다. `jsonschema`와 `fastjsonschema`는 영어이며, `jsonschema`는 경로를 별도 속성으로 줍니다. 메시지에 경로를 넣는 `fastjsonschema`(`data.evidence[0]...`)는 자체 검증기와 가깝습니다.

### httpx: 동작 차이 (로컬 서버로 재현)

- 404/429: `urllib`은 예외(`HTTPError`)를 던지고 `httpx`는 응답 객체를 돌려줍니다(`raise_for_status()`로 예외화). 오류 처리 코드를 다시 써야 합니다.
- 리다이렉트: `urllib`은 따라가고 `httpx`는 기본으로 따라가지 않습니다(302를 그대로 반환). `follow_redirects=True`가 필요합니다.
- 재시도: `HTTPTransport(retries=3)`은 연결 오류만 재시도합니다. 500, 500, 200을 돌려주는 서버에서 서버 호출이 1회였고 결과는 500이었습니다. 재시도가 필요하면 직접 구현해야 합니다.
- 타임아웃: 둘 다 정상 동작(`TimeoutError`와 `ReadTimeout`).
- 로컬 루프백 순차 20회: `urllib` 22ms, `httpx`(연결 재사용) 28ms. 연결 재사용 이득은 이 환경에서 관찰되지 않았습니다. HTTP/2(`h2`)는 설치하지 않아 검증하지 않았습니다.

### pydantic: 스키마 파생과 표현력

- 모델로 같은 계약을 만들면 24건 판정이 모두 일치했습니다(strict 모드, 항목 최소 길이 지정).
- 조건부 규칙(`completed`면 증거 필요, `partial/blocked`면 미해결 필요)은 `model_validator` 코드로만 존재합니다. 생성된 JSON Schema에는 들어가지 않아, 그 스키마로 검증하면 `completed` + 빈 `evidence`가 **통과**했습니다. 모델과 스키마 중 어느 쪽을 원본으로 삼든 규칙이 한쪽에서 사라집니다.
- 기본(lax) 모드는 `"5"`를 `5`로, `True`를 `1`로 변환합니다. 계약 검증에는 strict 지정이 필수입니다.
- 오류 메시지는 영어이며 항목별로 구조화되어 있습니다.

### pytest: 호환성과 실패 출력

- 기존 `unittest` 테스트 131개와 서브테스트 33개가 **수정 없이** 통과했습니다. 도입 비용은 사실상 0입니다.
- 실패 출력은 33줄 대 20줄로 pytest가 더 길지만 `Differing items` 등 구조 비교와 `-vv` 확장이 있습니다. `unittest`의 `assertEqual`도 차이 표시를 제공합니다. 병렬 실행(`pytest-xdist`)은 설치하지 않아 검증하지 않았습니다.

### typer: 같은 CLI를 재현

- 상호 배타 옵션(`--ids`와 `--from-specs`): argparse는 둘 다 주거나 둘 다 없으면 종료 코드 2로 거부했습니다. typer는 **둘 다 주어도, 둘 다 없어도 통과(종료 코드 0)** 했습니다. 직접 검증 코드를 써야 합니다.
- `--ids a b c`(공백 구분 다중 값): argparse는 통과했고 typer는 거부했습니다. `--ids a --ids b`로 바꿔야 해 기존 사용법이 깨집니다.
- 잘못된 정수는 둘 다 종료 코드 2로 거부했습니다.

## 종합 (속도 + 기능)

| 후보 | 속도 이득 | 기능 이득 | 위험·비용 | 판정 |
|---|---|---|---|---|
| orjson | 2~3배, 절대값 미미 | 없음 | 큰 정수 무음 변환, 반환형 bytes | 이득 부족. 보류 |
| fastjsonschema | 1.6배 | 오류 메시지에 경로 포함 | 2020-12 키워드 무음 무시 | 보류. 도입 시 지원 키워드 검사 필요 |
| jsonschema | 3.4배 느림 | 전체 문법 지원, 구조화 오류 | import 620ms | 스키마가 복잡해질 때만 선택 의존성 |
| httpx | 없음 | 비동기, 재시도 훅, HTTP/2 | 오류·리다이렉트 처리 재작성, 재시도 직접 구현 | 현재 규모에서는 이득 없음 |
| pydantic | 없음 | 모델로 타입·검증 | 조건부 규칙이 스키마에서 사라짐, lax 변환 | 계약의 원본으로는 부적합 |
| pytest | 느림 | 풍부한 출력, 확장 | 도입 비용 0 | 팀 선호 문제. 선택 사항 |
| typer | 느림 | 선언적 CLI | 상호 배타 옵션·다중 값 호환성 상실 | 비추천 |

## 채택 결정과 적용 (2026-11-02)

결정: `orjson`과 `httpx`는 채택, `pydantic`은 `jsonschema` 대용으로 재검토 후 계약 검증기로 채택. 나머지(`jsonschema`, `fastjsonschema`, `pytest`, `typer`)는 보류.

### 적용 범위와 경계

| 범위 | 라이브러리 | 이유 |
|---|---|---|
| `core/catalog`, `core/contract`, `adapters/hermes/export_model_map.py` | orjson (`core/jsonio.py` 경유), httpx, pydantic | 개발자 도구와 부모 쪽 검증. 외부 패키지 설치가 가능한 곳 |
| `core/eligibility/rules.py` 와 플러그인 사본 | **표준 라이브러리 유지** | `sync_plugin.py`가 Hermes 안으로 복사해 실행하므로 Hermes 환경에 패키지가 있다고 가정할 수 없다. 의존성 없는 `python3`에서 판정기·플러그인 테스트 65개가 통과함을 확인 |
| `adapters/hermes/apply_model_map.py` | 표준 `json` 유지 | 공백이 있는 `json.dumps` 출력을 YAML 줄에 그대로 넣는다. orjson 은 공백 없는 출력이라 결과가 달라진다 |

### 위험 대응

- **orjson 의 큰 정수 무음 변환:** `core/jsonio.py` 한 곳에서만 import 하고, `tests/test_jsonio.py`가 (1) 저장소 JSON 6개의 읽기·들여쓰기 쓰기가 표준 `json`과 동일함, (2) 저장소 데이터에 64비트 초과 정수와 NaN/무한대가 없음, (3) 차이점 동작이 바뀌면 알아챌 수 있도록 현재 동작을 고정한다.
- **httpx 의 동작 차이:** `core/catalog/_http.py`가 리다이렉트 추종, 4xx/5xx 예외화, 짧은 오류 문자열을 urllib 과 같게 맞춘다. 재시도는 추가하지 않았다(httpx 의 `retries`는 연결 오류만 재시도). 한 클라이언트를 스레드 간에 공유한다. `tests/test_catalog_http.py`가 로컬 서버로 이를 검증한다.
- **pydantic 의 lax 변환:** 모델은 `strict=True`, `extra="forbid"`. `end`는 `Optional`이 아니라 기본값 `None`으로 두어 생략은 허용하고 명시적 `null`은 스키마와 같이 거부한다.

### pydantic 재평가 결과 (`bench/eval_criteria.py`)

- **판정 일치:** 44건 코퍼스(경계 사례 포함)에서 원본 JSON Schema 와 `core.contract.validate`의 판정이 모두 일치했다. 독립 기준은 `jsonschema` 이다.
- **스키마 생성의 한계(재확인):** `Report.model_json_schema()`는 조건부 규칙이 없다. 코퍼스에서 모델이 거부하는 3건(`completed`+빈 증거 등)을 생성 스키마는 통과시켰다. 그래서 위임 도구에 넘기는 계약은 손으로 관리하는 원본 JSON Schema 파일이고, 모델은 같은 규칙을 코드로 유지한다. 어긋남은 필드·필수·열거값 구조 검사와 판정 일치 테스트가 막는다.
- **속도:** 24건 기준 pydantic 187µs, 기존 표준 라이브러리 검증기 357µs, `fastjsonschema` 224µs, `jsonschema` 1206µs. 가장 빠르다. import 는 약 235ms(중앙값)로 `orjson`(약 78ms)보다 무겁다.
- **오류 메시지:** 영어 문구에 필드 경로(`$.evidence[0].path_or_url`)를 붙여 반환한다. 이전 한국어 메시지는 사라졌다.
- **`validate()` 의 스키마 파일 읽기:** 모델이 검증하므로 스키마 파일을 읽지 않는다(이전 5ms 문제가 구조적으로 사라짐). 테스트가 이를 고정한다.
- **API 변경:** `validate(instance, schema=None)`의 `schema` 인자가 없어졌다. 임의 스키마를 넣어 검증하던 호출은 없었고, 이전 구현은 `bench/stdlib_validator.py`로 보존해 벤치 기준선으로만 쓴다.

### 실제 API 종단 확인

`inspect_endpoints.py`가 13건 모두 성공했고, `build_capabilities.py`로 재생성한 `model-capabilities.json`은 저장된 파일과 모델 13개 전부 값이 같았다. `export_model_map.py --check`는 `model-map-proposal.json` 23경로가 바이트 단위로 일치했다.
