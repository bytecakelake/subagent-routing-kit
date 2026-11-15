"""spawn_agent 호출을 core/eligibility 하드 규칙으로 검사한다. 표준 라이브러리만 사용한다(Python 3.11+).

순수 로직이다. Codex 를 import 하지 않는다. 판정 규칙은 core/eligibility/rules.py 사본(eligibility_rules.py)이다.

무엇을 아는가 -- 호출 인자(model, reasoning_effort, agent_type, items)와 프로젝트/사용자 custom agent TOML 뿐이다.
무엇을 모르는가 -- 최종 실제 모델·강도. 인자를 생략하면 부모/설정(agents.default_subagent_*)/역할이 정하고,
custom agent 가 호출 인자를 나중에 덮어쓸 수도 있다. 그래서 세 가지로 나눈다.
  1. 가능한 설정 조합 중 하나라도 규칙을 어기면 차단한다(호출 인자와 role 값을 모두 후보로 검사).
  2. 모든 후보가 통과해도 모델이나 강도를 알 수 없으면 "자격 불명"이다. unknown 정책에 따른다(기본 deny).
  3. 전부 알고 전부 통과하면 통과시킨다. 이는 "요청된 값이 자격 있음"이지 "최종 실행 모델 확정"이 아니다.
"""
from __future__ import annotations

import json
import pathlib
from typing import Mapping, Optional

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None  # type: ignore[assignment]

try:  # 플러그인 scripts/ 에서 실행될 때
    import eligibility_rules as rules
except ImportError:  # pragma: no cover - 패키지로 불러온 경우
    from . import eligibility_rules as rules  # type: ignore[no-redef]

SPAWN_SUFFIX = "spawn_agent"  # V1: spawn_agent, V2: collaborationspawn_agent (이름이 붙어 보고되는 경우)
SPAWN_ALIAS = "Agent"
IMAGE_ITEM_TYPES = frozenset({"image", "local_image"})
UNKNOWN_DENY, UNKNOWN_ALLOW = "deny", "allow"
HERE = pathlib.Path(__file__).resolve().parent


def is_spawn_tool(name) -> bool:
    if not isinstance(name, str) or not name:
        return False
    return name == SPAWN_ALIAS or name.endswith(SPAWN_SUFFIX)


def load_capabilities(path=None) -> dict:
    return rules.load_capabilities(path or HERE / "capabilities.json")


def _agent_dirs(cwd: Optional[str], codex_home: pathlib.Path) -> list:
    """project > user 순서. cwd 에서 위로 올라가며 .codex/agents 를 모으되 git 루트(.git)에서 멈춘다."""
    dirs = []
    if cwd:
        cur = pathlib.Path(cwd)
        for d in (cur, *cur.parents):
            if (d / ".codex" / "agents").is_dir():
                dirs.append(d / ".codex" / "agents")
            if (d / ".git").exists():
                break
    dirs.append(codex_home / "agents")
    return dirs


def find_role(name: str, cwd: Optional[str], codex_home: pathlib.Path):
    """name 필드가 일치하는 custom agent TOML 을 찾는다. 못 찾거나 읽을 수 없으면 None."""
    if tomllib is None:
        return None
    for directory in _agent_dirs(cwd, codex_home):
        for path in sorted(directory.glob("*.toml")):
            try:
                doc = tomllib.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(doc, dict) and doc.get("name") == name:
                return {"path": path, "model": doc.get("model"),
                        "reasoning_effort": doc.get("model_reasoning_effort")}
    return None


def _text(value) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _needs_image(tool_input: Mapping) -> bool:
    items = tool_input.get("items")
    return isinstance(items, list) and any(
        isinstance(i, Mapping) and i.get("type") in IMAGE_ITEM_TYPES for i in items)


def check(payload: Mapping, caps: Mapping, *, codex_home, unknown: str = UNKNOWN_DENY) -> Optional[str]:
    """차단할 이유가 있으면 메시지를, 없으면 None 을 돌려준다."""
    if not isinstance(payload, Mapping) or not is_spawn_tool(payload.get("tool_name")):
        return None
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            tool_input = None
    if not isinstance(tool_input, Mapping):
        return _unknown_msg(["tool_input is not an object"], unknown)

    models, efforts, notes = [], [], []
    role = None
    role_name = _text(tool_input.get("agent_type"))
    unresolved = False
    if role_name:
        role = find_role(role_name, payload.get("cwd"), pathlib.Path(codex_home))
        if role is None:
            unresolved = True
            notes.append(f"agent_type '{role_name}' is not a custom agent file found under .codex/agents "
                         f"(built-in or config.toml roles are not visible to this hook)")
    call_model, call_effort = _text(tool_input.get("model")), _text(tool_input.get("reasoning_effort"))
    role_model = _text(role and role["model"])
    role_effort = _text(role and role["reasoning_effort"])
    for source, value, bucket in (("call", call_model, models), ("custom agent", role_model, models),
                                  ("call", call_effort, efforts), ("custom agent", role_effort, efforts)):
        if value and value not in [v for _, v in bucket]:
            bucket.append((source, value))

    # 1) 가능한 조합 중 위반이 있으면 차단 -- 호출 인자와 role 값 중 어느 쪽이 이길지 이 훅은 모른다.
    task = rules.Task(id="spawn", needs_modalities=frozenset({"text", "image"} if _needs_image(tool_input)
                                                             else {"text"}))
    violations = []
    for m_src, model in models:
        for e_src, effort in (efforts or [("omitted", None)]):
            # 강도를 모르면 모델 자체의 자격(알려진 모델인지, 모달리티)만 본다. effort_implicit 은 아래 "자격 불명"으로 다룬다.
            route = rules.Route("spawn", model, effort or _any_effort(caps, model), "normal")
            decision = rules.evaluate(task, [route], caps, registered=["spawn"])
            for code in decision.rejected.get("spawn", ()):
                violations.append((code, model, effort, m_src, e_src))
    if violations:
        return _violation_msg(violations, role_name if role else None)

    # 2) 자격 불명
    missing = []
    if not models:
        missing.append("model")
    if not efforts:
        missing.append("reasoning_effort")
    if missing or unresolved:
        reasons = ([f"{' and '.join(missing)} not specified by the call or a resolvable custom agent"]
                   if missing else []) + notes
        return _unknown_msg(reasons, unknown)
    return None


def _any_effort(caps: Mapping, model: str):
    """강도가 불명일 때 모델 자격만 보려고 쓰는 대리값. 모델이 모르는 모델이면 None(규칙이 unknown_model 로 거른다)."""
    c = caps.get(model)
    return c.supported_efforts[0] if c is not None and c.supported_efforts else None


def _violation_msg(violations, role_name) -> str:
    seen, lines = set(), []
    for code, model, effort, m_src, e_src in violations:
        key = (code, model, effort)
        if key in seen:
            continue
        seen.add(key)
        where = f"model '{model}' (from {m_src})"
        if effort is not None:
            where += f", reasoning_effort '{effort}' (from {e_src})"
        lines.append(f"- {code}: {where}")
    head = "spawn_agent blocked by routing hard rules (subagent-routing-kit)"
    tail = ["Use a model/effort listed in the plugin's capability snapshot (scripts/capabilities.json), or do the work directly."]
    if role_name:
        tail.insert(0, f"Both the call arguments and custom agent '{role_name}' are checked because a custom agent may "
                       "override the call's model settings; the hook cannot tell which wins.")
    tail.append("This checks requested settings only; it does not prove the final model a subagent runs with.")
    return "\n".join([head, *lines, *tail])


def _unknown_msg(reasons, unknown) -> Optional[str]:
    if unknown == UNKNOWN_ALLOW:
        return None
    return "\n".join([
        "spawn_agent blocked: eligibility unknown (subagent-routing-kit)",
        *[f"- {r}" for r in reasons],
        "The final model and reasoning effort cannot be determined from this call, so the hard rules cannot be applied.",
        "Pass explicit `model` and `reasoning_effort`, or use `agent_type` naming a custom agent in .codex/agents/*.toml "
        "that sets both `model` and `model_reasoning_effort`. "
        "To let unknown cases through, set SUBAGENT_ROUTING_UNKNOWN=allow in the Codex environment.",
    ])
