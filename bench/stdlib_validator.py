"""벤치 기준선: main 의 표준 라이브러리 전용 계약 검증기 사본(core.contract 가 pydantic 으로 바뀐 뒤에도 비교할 수 있게 보존한다).

외부 jsonschema 패키지 없이도 계약을 강제할 수 있도록, 이 저장소의 스키마가 쓰는 키워드만 구현한다.
지원: type, enum, const, required, properties, additionalProperties, items, minLength, minItems,
allOf, if/then. 지원하지 않는 키워드를 만나면 조용히 통과시키지 않고 예외를 던진다.
검증을 통과해도 증거나 산출물의 사실 여부는 확인되지 않는다. 그것은 부모가 따로 검증한다.
"""
import functools
import json
import pathlib

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "core" / "spec" / "output-contract.schema.json"

_ANNOTATIONS = {"$schema", "$id", "title", "description"}
_SUPPORTED = _ANNOTATIONS | {
    "type", "enum", "const", "required", "properties", "additionalProperties",
    "items", "minLength", "minItems", "allOf", "if", "then",
}
_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
}


def load_schema(path=None):
    return json.loads(pathlib.Path(path or SCHEMA_PATH).read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def _default_schema():
    """기본 스키마는 한 번만 읽는다. 호출마다 읽으면 파일 I/O 가 검증 비용을 압도한다(약 5ms 대 17µs)."""
    return load_schema()


def validate(instance, schema=None):
    """위반 목록을 반환한다. 빈 목록이면 통과. 반환 전 스키마를 수정하지 않는다."""
    errors = []
    _check(instance, schema if schema is not None else _default_schema(), "$", errors)
    return errors


def parse_and_validate(text, schema=None):
    """자식이 돌려준 JSON 문자열을 파싱하고 검증한다. (값, 위반 목록)을 반환한다."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError as e:
        return None, [f"$: JSON 이 아닙니다 ({e.msg}, {e.lineno}행 {e.colno}열)"]
    return value, validate(value, schema)


def _check(value, schema, path, errors):
    unknown = set(schema) - _SUPPORTED
    if unknown:
        raise ValueError(f"지원하지 않는 스키마 키워드: {sorted(unknown)}")
    if "type" in schema and not _TYPES[schema["type"]](value):
        errors.append(f"{path}: {schema['type']} 이어야 합니다")
        return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: {schema['const']!r} 이어야 합니다")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {schema['enum']} 중 하나여야 합니다 (받은 값: {value!r})")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{path}: 길이가 {schema['minLength']} 이상이어야 합니다")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: 항목이 {schema['minItems']}개 이상이어야 합니다")
        if "items" in schema:
            for i, item in enumerate(value):
                _check(item, schema["items"], f"{path}[{i}]", errors)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: 필수 필드 {key!r} 가 없습니다")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: 허용되지 않은 필드 {key!r}")
        for key, sub in props.items():
            if key in value:
                _check(value[key], sub, f"{path}.{key}", errors)
    for sub in schema.get("allOf", []):
        _check(value, sub, path, errors)
    if "if" in schema:
        probe = []
        _check(value, schema["if"], path, probe)
        if not probe and "then" in schema:
            _check(value, schema["then"], path, errors)
