#!/usr/bin/env python3
"""설치된 Hermes 가 이 저장소의 model_map 제안을 의도대로 해석하는지 오프라인으로 검사한다.

추론 호출을 하지 않는다. 설치된 Hermes 소스의 변환 함수를 수정 없이 실행한다.
Hermes 소스 경로가 필요하다: --hermes-home 또는 환경 변수 HERMES_HOME
(<hermes-home>/hermes-agent, <hermes-home>/plugins/advanced-delegation/model_map.py 를 사용)

\b
python adapters/hermes/validate_installed.py --hermes-home /hermes-home [--out validation/installed-probes.json]

이 검사는 설치된 버전에 의존한다. 버전이 바뀌면 다시 실행해야 하며, 통과가 실제 호출 성공을 뜻하지는 않는다.
"""
import ast
import json
import logging
import pathlib
import sys
import typing
from types import SimpleNamespace
from typing import Annotated, Optional

import typer
from pydantic import DirectoryPath

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # 스크립트로 직접 실행해도 core 를 import 할 수 있게 한다

from core import cliutil  # noqa: E402

PROPOSAL = ROOT / "adapters" / "hermes" / "model-map-proposal.json"
PLUGIN_NAMES = {"BACKEND", "SETTINGS_PATH", "ROUTE_FIELDS", "_warned"}
PLUGIN_FUNCS = {"_warn_once", "_text", "_entry_problem", "configured_options"}


def load_plugin_parser(model_map_py):
    """플러그인 전체를 import 하지 않고(선택 의존성 때문에) 옵션 파서 함수만 원문 그대로 컴파일한다."""
    tree = ast.parse(pathlib.Path(model_map_py).read_text(encoding="utf-8"))
    body = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in PLUGIN_FUNCS:
            body.append(n)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            if any(isinstance(t, ast.Name) and t.id in PLUGIN_NAMES for t in targets):
                body.append(n)
    found = {n.name for n in body if isinstance(n, ast.FunctionDef)}
    if found != PLUGIN_FUNCS:
        raise SystemExit(f"플러그인에서 함수를 찾지 못함: {sorted(PLUGIN_FUNCS - found)} (플러그인 구조가 바뀌었을 수 있음)")
    ns = {"Any": typing.Any, "Mapping": typing.Mapping, "logger": logging.getLogger("probe")}
    exec(compile(ast.Module(body=body, type_ignores=[]), "installed-model-map", "exec"), ns)
    return ns


def load_inheritance(config_py):
    tree = ast.parse(pathlib.Path(config_py).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
             and n.name in ("ResolvedReasoning", "_child_reasoning")]
    ns = {"NamedTuple": typing.NamedTuple, "Optional": typing.Optional, "Any": typing.Any,
          "logger": logging.getLogger("probe")}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "installed-inheritance", "exec"), ns)
    return ns["_child_reasoning"]


def run(hermes_home):
    home = pathlib.Path(hermes_home)
    agent_dir = home / "hermes-agent"
    plugin = home / "plugins" / "advanced-delegation" / "model_map.py"
    for p in (agent_dir, plugin):
        if not p.exists():
            raise SystemExit(f"없는 경로: {p}")
    sys.path.insert(0, str(agent_dir))
    from hermes_constants import parse_reasoning_effort  # noqa: E402
    from tools.delegate_tool_tuning import task_service_tier  # noqa: E402

    checks = []

    def check(name, ok):
        checks.append({"name": name, "passed": bool(ok)})

    check("actual-none-means-disabled", parse_reasoning_effort("none") == {"enabled": False})
    pin = task_service_tier("normal", {"provider": "openrouter", "model": "qwen/qwen3.8-flash",
                                       "request_overrides": {"service_tier": "priority",
                                                             "extra_body": {"speed": "fast", "retain": 1}}},
                            SimpleNamespace())
    check("actual-normal-clears-inherited-speed",
          pin["request_overrides"] == {"extra_body": {"retain": 1}} and pin["service_tier"] is None)

    child_reasoning = load_inheritance(agent_dir / "tools" / "delegate_tool_config.py")
    parent = SimpleNamespace(reasoning_config={"enabled": True, "effort": "high"})
    check("actual-missing-route-inherits-global",
          child_reasoning(parent, {"reasoning_effort": "medium"}, None) == {"enabled": True, "effort": "medium"})
    check("actual-missing-route-inherits-parent", child_reasoning(parent, {}, None) == parent.reasoning_config)
    check("actual-explicit-none-blocks-inheritance",
          child_reasoning(parent, {"reasoning_effort": "medium"}, "none") == {"enabled": False})

    # 설치된 플러그인의 옵션 파서가 제안 파일을 어떻게 읽는지 확인한다
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    parsed = load_plugin_parser(plugin)["configured_options"]({"options": proposal["options"]})
    names = [o["name"] for o in proposal["options"]]
    routes = [parsed[n]["route"] for n in parsed]
    check("installed-parser-keeps-every-option-in-order", list(parsed) == names)
    check("installed-parser-keeps-explicit-effort-and-tier",
          all(r.get("reasoning_effort") and r.get("service_tier") == "normal" for r in routes))
    check("installed-parser-keeps-explicit-empty-fallback",
          all(r.get("fallback_providers") == [] for r in routes))
    check("proposal-default-is-an-option", proposal["default"] in parsed)
    return {"kind": "installed Hermes conversion-function probes, NOT inference",
            "checks": checks, "passed": sum(c["passed"] for c in checks), "count": len(checks),
            "routes": len(names), "unique_models": len({o["model"] for o in proposal["options"]})}


class Args(cliutil.Args):
    hermes_home: DirectoryPath
    out: Optional[pathlib.Path] = None


app = cliutil.make_app()


@app.command(help=__doc__)
def main(
    hermes_home: Annotated[Optional[pathlib.Path], typer.Option(envvar="HERMES_HOME", help="Hermes 홈 폴더. 환경 변수 HERMES_HOME 으로도 지정")] = None,
    out: Annotated[Optional[pathlib.Path], typer.Option(help="결과 JSON 저장 경로(생략하면 출력만)")] = None,
):
    if hermes_home is None:
        raise typer.BadParameter("--hermes-home 또는 환경 변수 HERMES_HOME 이 필요합니다")
    a = cliutil.parse_args(Args, hermes_home=hermes_home, out=out)
    result = run(a.hermes_home)
    for c in result["checks"]:
        print(("PASS " if c["passed"] else "FAIL ") + c["name"])
    print(f"{result['passed']}/{result['count']} passed")
    if a.out:
        a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if result["passed"] != result["count"]:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
