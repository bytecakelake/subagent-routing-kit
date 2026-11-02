"""자식 에이전트 보고(출력 계약) 검증. pydantic 모델이 런타임 검증기이다.

원본 계약은 core/spec/output-contract.schema.json 이다. 위임 도구에 넘기는 JSON Schema 는 이 파일을
그대로 쓰고, 이 모듈은 같은 판정을 내리는 모델을 코드로 유지한다. 둘이 어긋나지 않도록
tests/test_output_contract.py 가 필드·필수·열거값 일치와 판정 일치(jsonschema 가 있을 때)를 검사한다.

모델을 스키마에서 생성하지 않는 이유: pydantic 이 생성한 스키마에는 조건부 규칙(completed 는 증거 필요,
partial/blocked 는 미해결 필요)이 들어가지 않는다. 그 스키마로 검증하면 규칙이 사라진다.
strict 모드를 쓰는 이유: 기본(lax) 모드는 "5"를 5로, True를 1로 바꿔 통과시킨다.
검증을 통과해도 증거나 산출물의 사실 여부는 확인되지 않는다. 그것은 부모가 따로 검증한다.
"""
import pathlib
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core import jsonio

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "spec" / "output-contract.schema.json"

NonEmpty = Annotated[str, Field(min_length=1)]
END_VALUES = ("criteria met", "insufficient evidence", "permission/environment blocker", "assigned scope exhausted")


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path_or_url: NonEmpty
    check: NonEmpty


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["completed", "partial", "blocked"]
    # Optional 이 아니다: 생략은 허용하되 명시적 null 은 스키마(type: string)와 같이 거부한다.
    end: Literal[END_VALUES] = None  # type: ignore[assignment]
    result: NonEmpty
    evidence: list[Evidence]
    artifacts: list[NonEmpty] = []
    checks: list[NonEmpty] = []
    unresolved: list[NonEmpty]
    scope_changes: list[NonEmpty] = []

    @model_validator(mode="after")
    def _conditional_rules(self):
        if self.status == "completed" and not self.evidence:
            raise ValueError("completed 는 evidence 가 1개 이상이어야 합니다")
        if self.status in ("partial", "blocked") and not self.unresolved:
            raise ValueError(f"{self.status} 는 unresolved 가 1개 이상이어야 합니다")
        return self


def load_schema(path=None):
    """위임 도구에 넘기거나 검토할 JSON Schema 를 읽는다. validate() 는 이 파일을 읽지 않는다."""
    return jsonio.load_path(path or SCHEMA_PATH)


def _path(loc):
    out = "$"
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def validate(instance):
    """위반 목록을 반환한다. 빈 목록이면 통과."""
    try:
        Report.model_validate(instance)
    except ValidationError as e:
        return [f"{_path(err['loc'])}: {err['msg']}" for err in e.errors()]
    return []


def parse_and_validate(text):
    """자식이 돌려준 JSON 문자열을 파싱하고 검증한다. (값, 위반 목록)을 반환한다."""
    try:
        value = jsonio.loads(text)
    except jsonio.JSONDecodeError as e:
        return None, [f"$: JSON 이 아닙니다 ({e.msg}, {e.lineno}행 {e.colno}열)"]
    return value, validate(value)
