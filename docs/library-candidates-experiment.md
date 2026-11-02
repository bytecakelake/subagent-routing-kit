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

### typer: 같은 CLI를 재현 (초기 측정, 아래 재평가로 정정됨)

초기 측정은 상호 배타 검사를 구현하지 않은 채 비교해서, "둘 다 주어도 통과"를 typer의 결함처럼 적었다. 이는 공정하지 않았다. 아래 재평가를 보라.

## 종합 (속도 + 기능)

| 후보 | 속도 이득 | 기능 이득 | 위험·비용 | 판정 |
|---|---|---|---|---|
| orjson | 2~3배, 절대값 미미 | 없음 | 큰 정수 무음 변환, 반환형 bytes | 이득 부족. 보류 |
| fastjsonschema | 1.6배 | 오류 메시지에 경로 포함 | 2020-12 키워드 무음 무시 | 보류. 도입 시 지원 키워드 검사 필요 |
| jsonschema | 3.4배 느림 | 전체 문법 지원, 구조화 오류 | import 620ms | 스키마가 복잡해질 때만 선택 의존성 |
| httpx | 없음 | 비동기, 재시도 훅, HTTP/2 | 오류·리다이렉트 처리 재작성, 재시도 직접 구현 | 현재 규모에서는 이득 없음 |
| pydantic | 없음 | 모델로 타입·검증 | 조건부 규칙이 스키마에서 사라짐, lax 변환 | 계약의 원본으로는 부적합 |
| pytest | 느림 | 풍부한 출력, 확장 | 도입 비용 0 | 팀 선호 문제. 선택 사항 |
| typer | 느림 | 선언적 CLI | 아래 재평가 참고 | 재평가: 보류 |

## 채택 결정과 적용 (2026-11-02)

결정: `orjson`과 `httpx`는 채택, `pydantic`은 `jsonschema` 대용으로 재검토 후 계약 검증기로 채택. 나머지(`jsonschema`, `fastjsonschema`, `pytest`, `typer`)는 보류.

### 적용 범위와 경계

| 범위 | 라이브러리 | 이유 |
|---|---|---|
| `core/catalog`, `core/contract`, `adapters/hermes/export_model_map.py` | orjson (`core/jsonio.py` 경유), httpx, pydantic | 개발자 도구와 부모 쪽 검증. 외부 패키지 설치가 가능한 곳 |
| `core/eligibility/rules.py` 와 플러그인 사본 | **표준 라이브러리 유지** | `sync_plugin.py`가 Hermes 안으로 복사해 실행하므로 Hermes 환경에 패키지가 있다고 가정할 수 없다. 의존성 없는 `python3`에서 판정기·플러그인 테스트 65개가 통과함을 확인 |
| `adapters/hermes/apply_model_map.py` | orjson (`core/jsonio.py` 경유) | 처음에는 공백 없는 출력이 YAML 에 문제를 줄까 봐 제외했으나, 공백 없는 JSON 도 유효한 YAML 흐름 표기이며 PyYAML 로 읽으면 이전 출력과 같은 데이터임을 확인해 적용했다(현재 23경로에서는 텍스트까지 동일). orjson 에는 `, `/`: ` 공백을 넣는 옵션이 없고 `OPT_INDENT_2`(여러 줄)뿐이다 |

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
- **API 변경:** `validate(instance, schema=None)`의 `schema` 인자가 없어졌다. 임의 스키마를 넣어 검증하던 호출은 없었고, 이전 구현은 보존하지 않고 삭제했다(git 이력: `main`의 `37cb18b`). 위 속도 표의 자체 검증기 수치는 그 구현의 측정 기록이다.

### 실제 API 종단 확인

`inspect_endpoints.py`가 13건 모두 성공했고, `build_capabilities.py`로 재생성한 `model-capabilities.json`은 저장된 파일과 모델 13개 전부 값이 같았다. `export_model_map.py --check`는 `model-map-proposal.json` 23경로가 바이트 단위로 일치했다.

## typer 재평가 (공식 문서 기준)

근거 문서: typer.tiangolo.com 의 `tutorial/multiple-values/multiple-options`, `arguments-with-multiple-values`, `options-with-multiple-values`, 그리고 상호 배타 옵션에 대한 `fastapi/typer#140`. 설치된 typer 0.27.3 의 소스(click 은 `typer/_click`에 내장)에서 mutually/exclusive 관련 기능을 검색해 없음을 확인했고, `typer.Option`에 `nargs` 매개변수가 없음도 확인했다.

### 문서가 말하는 것

- 여러 값: `list[str]` 옵션은 **반복 옵션**(`--user a --user b`)으로 받는다. 옵션 하나 뒤에 공백으로 이은 가변 개수 값(`--ids a b c`)은 문서에 없다. 가변 개수는 **마지막 위치 인자**의 `list`로만 받고, 옵션이 받는 여러 값은 개수가 고정된 `tuple`이다.
- 상호 배타: 공식 기능이 아니다. 이슈 #140 의 답은 Enum 으로 대체하거나 콜백/본문에서 직접 검사하라는 것이다. "하나는 필수"도 본문에서 검사한다.

### 문서 방식으로 같은 CLI 를 구현해 다시 측정 (`bench/eval_criteria.py`)

| 입력 | argparse (현재) | typer 방식 1: 반복 옵션 + 본문 검사 | typer 방식 2: 위치 인자 |
|---|---|---|---|
| `--ids a b c` (현재 문서의 사용법) | 통과 | **거부**(unexpected extra argument) | `--ids` 옵션 자체가 없음 |
| `--ids a --ids b` | 통과하지만 **`b`만 남고 `a`는 조용히 버려짐** | 통과, `a`와 `b` 모두 수집 | 해당 없음 |
| 위치 인자 `a b c` | 거부 | 거부 | 통과 |
| `--ids`와 `--from-specs` 둘 다 | 거부(코드 2) | 거부(코드 2, 직접 구현한 검사) | 해당 없음 |
| 둘 다 없음 | 거부(코드 2) | 거부(코드 2, 직접 구현한 검사) | 거부(코드 2) |
| `--out` 없음, `--timeout abc`, 알 수 없는 옵션 | 거부 | 거부(메시지는 rich 상자) | 해당 없음 |

- 상호 배타 검사는 약 5줄을 직접 쓰면 argparse 와 같은 판정(종료 코드 2)이 된다. 정의 길이는 argparse 8줄 대 typer 12줄이다.
- 정정: argparse 의 `--ids a --ids b` 는 마지막 값만 남기는 동작이 있어, 반복 옵션 방식이 오히려 값을 잃지 않는다.
- 호환성: 현재 `inspect_endpoints.py`의 문서화된 사용법(`--ids openai/gpt-6-luna nvidia/...`)은 깨진다. 호출을 `--ids a --ids b`로 바꿔야 한다.
- 비용: `import typer`는 측정마다 중앙값 약 375~557ms(기본 기동 약 32~35ms)로 변동이 크고 `rich`, `shellingham`, `annotated-doc`(Windows는 `colorama` 포함)와 `rich`의 하위 의존성이 추가된다. 저장소의 CLI 스크립트는 7개이고 `add_argument`는 23곳이다.
- 얻는 것: rich 로 꾸민 도움말과 오류, 셸 자동완성(`add_completion` 기본 켜짐), 반복 옵션의 값 보존. 이 저장소의 스크립트는 단발 실행이라 대부분 체감 이득이 작다.

### 재평가 결론

초기의 "비추천" 근거 중 상호 배타 문제는 구현 누락에서 나온 과장이었고 직접 검사를 쓰면 동등해진다. 남는 실제 차이는 (1) 기존 사용법 `--ids a b c` 호환성 상실, (2) 기동 시간과 의존성 증가, (3) 반복 옵션 값 보존과 자동완성 같은 부가 이득이다. 판정은 **보류**: 사용법 변경과 기동 비용을 감수할 만한 부가 이득(자동완성, 도움말)이 필요할 때만 도입한다.

### typer 와 pydantic 연동 (추가 확인)

- typer 0.27.3 자체에는 pydantic 연동이 없다. 의존성에 없고, 소스의 pydantic 언급은 1.9.2 에서 복사한 타입 유틸의 주석뿐이다. typer 의 자체 검사는 타입 힌트 변환, `min`/`max`, `exists` 등 경로 검사, `callback`, `parser`, `click_type` 이다.
- 그러나 pydantic 으로 인자를 검사하는 방법은 둘 다 동작했다(`BadParameter` 로 바꾸면 종료 코드 2).
  1. 본문에서 파싱된 값을 pydantic 모델에 넣어 검증: `model_validator` 로 "`--ids`와 `--from-specs` 중 정확히 하나" 같은 상호 배타를 선언하고, 항목의 정규식 같은 형식 검사도 모델에 둔다.
  2. `typer.Option(parser=...)` 에 `TypeAdapter` 를 연결해 값 하나씩 검사.
- 서드파티 브리지 `typantic`(0.8.1, 의존성 pydantic·pyyaml·typer)은 pydantic 모델에서 typer CLI 를 만들고 검증기를 그대로 적용했다. 상호 배타, 형식 오류, 잘못된 정수 모두 종료 코드 2로 거부했다. 이 패키지는 이번에 처음 써 봤고 성숙도·유지 상태는 검증하지 않았다.
- 어느 방식이든 `--ids a b c`(공백 구분)는 여전히 거부된다. 이 제약은 typer 의 파서 구조에서 오므로 pydantic 으로 해결되지 않는다.
- pydantic 으로 인자 값을 검사하는 일은 typer 에 의존하지 않는다. argparse 가 파싱한 값을 같은 모델에 넣어도 되므로, 이 연동이 typer 도입의 근거가 되지는 않는다(이 문장은 구조상의 추론이며 argparse 로는 실행해 보지 않았다).
