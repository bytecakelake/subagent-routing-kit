#!/usr/bin/env python3
"""core/spec 의 변형 명세를 Hermes advanced-delegation 의 model_map 옵션으로 변환한다.

원본은 core/spec/variant-specs.json 이다. 이 스크립트는 변환과 Hermes 고유 제약 검사만 한다.
경로 자격 판정은 core/eligibility 에 맡긴다. JSON 쓰기에 orjson 을 쓰며 추론 호출은 하지 않는다.

\b
python adapters/hermes/export_model_map.py            # model-map-proposal.json 을 다시 만든다
python adapters/hermes/export_model_map.py --check    # 파일을 건드리지 않고 최신인지만 검사한다
"""
import pathlib
import sys
from typing import Annotated

import typer
from pydantic import FilePath

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import cliutil, jsonio  # noqa: E402
from core.eligibility import Task, evaluate, load_capabilities, routes_from_specs  # noqa: E402

PROVIDER = "openrouter"
DEFAULT_ROUTE = "M-Haiku-Balanced"
# 설치된 model_map 이 한 옵션에서 읽는 키. 그 밖의 키는 조용히 버려지므로 내보내기 전에 막는다.
ALLOWED_KEYS = frozenset({"name", "description", "provider", "model", "reasoning_effort",
                          "service_tier", "fallback_providers"})
SPECS = ROOT / "core" / "spec" / "variant-specs.json"
CAPS = ROOT / "core" / "spec" / "model-capabilities.json"
OUT = ROOT / "adapters" / "hermes" / "model-map-proposal.json"


def describe(s):
    measured = "measured" if s.get("latency_measured") else "unmeasured"
    return (f"{s['use_when']}. Avoid: {s['avoid_when']}. "
            f"reasoning={s['reasoning_effort']}; speed={s['service_tier']}({s['latency_intent']}, {measured}).")


def build_options(specs):
    return [dict(name=s["name"], description=describe(s), provider=PROVIDER, model=s["model"],
                 reasoning_effort=s["reasoning_effort"], service_tier=s["service_tier"], fallback_providers=[])
            for s in specs]


def problems(options, default, specs_path=SPECS, caps_path=CAPS):
    """Hermes 고유 제약 + core 하드 규칙. 문제 목록을 돌려준다(비어 있으면 통과)."""
    errs = []
    names = [o.get("name") for o in options]
    if len(names) != len(set(names)):
        errs.append("옵션 이름이 중복됨")
    if default not in names:
        errs.append(f"기본 경로 {default!r} 가 옵션에 없음")
    for o in options:
        extra = set(o) - ALLOWED_KEYS
        if extra:
            errs.append(f"{o.get('name')}: model_map 이 읽지 않는 키 {sorted(extra)}")
        if o.get("provider") != PROVIDER:
            errs.append(f"{o.get('name')}: provider 가 {PROVIDER} 가 아님")
        if o.get("fallback_providers") != []:
            errs.append(f"{o.get('name')}: 폴백 정책이 명시적으로 비어 있어야 함")
    # 같은 이름의 옵션이 명세와 일치해야 하며, 자격 판정은 core 가 한다.
    specs = {r.name: r for r in routes_from_specs(specs_path)}
    for o in options:
        s = specs.get(o.get("name"))
        if s is None or (s.model, s.reasoning_effort, s.service_tier) != (
                o.get("model"), o.get("reasoning_effort"), o.get("service_tier")):
            errs.append(f"{o.get('name')}: 명세와 다른 옵션")
    d = evaluate(Task("export", needs_tools=True), list(specs.values()), load_capabilities(caps_path),
                 registered=names)
    for name, reasons in d.rejected.items():
        errs.append(f"{name}: 하드 규칙 위반 {list(reasons)}")
    return errs


def render(specs, default=DEFAULT_ROUTE):
    options = build_options(specs)
    errs = problems(options, default)
    if errs:
        raise SystemExit("내보내기 중단:\n  " + "\n  ".join(errs))
    return jsonio.dumps({"options": options, "default": default}, indent=True) + "\n"


class Args(cliutil.Args):
    specs: FilePath
    out: pathlib.Path
    default: str
    check: bool


app = cliutil.make_app()


@app.command(help=__doc__)
def main(
    specs: Annotated[pathlib.Path, typer.Option(help="variant-specs.json 경로", show_default="core/spec/variant-specs.json")] = SPECS,
    out: Annotated[pathlib.Path, typer.Option(help="model-map 제안 파일 경로", show_default="adapters/hermes/model-map-proposal.json")] = OUT,
    default: Annotated[str, typer.Option(help="model_map 의 기본 경로 이름")] = DEFAULT_ROUTE,
    check: Annotated[bool, typer.Option("--check", help="파일을 쓰지 않고 현재 파일이 최신인지 검사")] = False,
):
    a = cliutil.parse_args(Args, specs=specs, out=out, default=default, check=check)
    spec_list = jsonio.load_path(a.specs)
    text = render(spec_list, a.default)
    if a.check:
        have = a.out.read_text(encoding="utf-8") if a.out.exists() else None
        if have != text:
            print(f"DRIFT: {a.out} 가 명세와 다릅니다. 인자 없이 다시 실행해 갱신하십시오.")
            raise typer.Exit(1)
        print(f"OK: {a.out.name} 가 명세와 일치 ({len(spec_list)} 경로)")
        return
    a.out.write_text(text, encoding="utf-8")
    print(f"wrote {a.out}: {len(spec_list)} routes, default={a.default}")


if __name__ == "__main__":
    app()
