"""JSON 읽기·쓰기 래퍼(orjson). 한 곳에 모아 두어 차이점을 이 파일에서만 관리한다.

표준 `json` 과 다른 점(실험으로 확인):
- 64비트를 넘는 정수를 읽으면 예외 없이 float 로 바뀐다. 이 저장소의 데이터에는 없으며
  tests/test_jsonio.py 가 명세 파일에서 그런 값이 없음을 검사한다. 외부 입력을 읽을 때는 주의한다.
- NaN/Infinity 는 읽기 오류, 쓰기는 null.
- 정수 키, 단독 서로게이트, 64비트 초과 정수를 쓰면 TypeError.
들여쓰기 출력은 json.dumps(indent=2, ensure_ascii=False) 와 바이트 단위로 같다.
에이전트 호스트 안으로 복사되어 실행되는 코드(core/eligibility/rules.py와 그 사본)는 외부 패키지에 기대지 않도록 이 모듈을 쓰지 않는다.
"""
import pathlib

import orjson

JSONDecodeError = orjson.JSONDecodeError  # json.JSONDecodeError 의 하위 클래스


def loads(data):
    """str 또는 bytes 를 파싱한다."""
    return orjson.loads(data)


def load_path(path):
    return orjson.loads(pathlib.Path(path).read_bytes())


def dumps(obj, *, indent=False, sort_keys=False) -> str:
    """JSON 문자열. indent=True 는 2칸 들여쓰기. 끝에 개행을 붙이지 않는다."""
    option = 0
    if indent:
        option |= orjson.OPT_INDENT_2
    if sort_keys:
        option |= orjson.OPT_SORT_KEYS
    return orjson.dumps(obj, option=option or None).decode("utf-8")
