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
