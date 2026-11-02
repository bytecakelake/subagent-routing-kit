"""CLI 공통: typer 앱 생성과 pydantic 인자 검증.

typer 는 타입 변환과 필수 옵션 검사를 맡고, 값 사이의 규칙(상호 배타, 의존 관계, 범위, 파일 존재)은
Args 하위 모델이 선언한다. typer 에는 pydantic 연동이 없으므로 명령 본문에서 parse_args 로 연결한다.
검증 오류는 typer.BadParameter 로 바뀌어 종료 코드 2와 사용법 안내가 나온다.
"""
import typer
from pydantic import BaseModel, ConfigDict, ValidationError


class Args(BaseModel):
    """CLI 인자 모델의 기반. 모르는 필드를 거부하고 값을 바꾸지 못하게 한다."""
    model_config = ConfigDict(extra="forbid", frozen=True)


def make_app():
    # 스크립트 용도라 자동완성 설치 옵션과 rich 서식(상자, 색 마크업)을 끈다.
    return typer.Typer(add_completion=False, pretty_exceptions_enable=False, rich_markup_mode=None)


def _where(loc):
    if not loc:
        return ""
    name, rest = str(loc[0]), loc[1:]
    return "--" + name.replace("_", "-") + "".join(f"[{i}]" for i in rest)


def _describe(err):
    msg = err["msg"].removeprefix("Value error, ")
    if err["type"].startswith("path_"):
        msg += f": {err['input']}"
    where = _where(err["loc"])
    return f"{where}: {msg}" if where else msg


def parse_args(model, **values):
    """값을 모델로 검증해 돌려준다. 위반하면 typer.BadParameter (종료 코드 2)."""
    try:
        return model(**values)
    except ValidationError as e:
        raise typer.BadParameter("; ".join(_describe(x) for x in e.errors())) from None
