"""delegate_task 실행 전에 경로 자격을 코드로 검사한다. 표준 라이브러리만 사용한다.

이 모듈은 순수 로직이다. Hermes 를 import 하지 않으므로 테스트에서 그대로 호출할 수 있다.
판정 규칙은 core/eligibility/rules.py 사본(eligibility_rules.py)을 쓴다. 사본은
`python adapters/hermes/sync_plugin.py` 로 갱신하며, 테스트가 원본과 일치하는지 검사한다.
"""
from __future__ import annotations

import logging
from typing import Mapping, Optional

try:  # 플러그인으로 로드될 때
    from . import eligibility_rules as rules
except ImportError:  # 단독 실행·테스트에서 플러그인 폴더를 sys.path 에 넣은 경우
    import eligibility_rules as rules  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

TOOL = "delegate_task"
CONTROL_ACTIONS = frozenset({"list", "steer", "stop"})
BACKEND = "model_map"
FALLBACK_VIOLATION = rules.FREE_TO_PAID_FALLBACK


def _block(config: Mapping) -> Mapping:
    dep = config.get("delegation") or {}
    return ((dep.get("backends") or {}).get(BACKEND) or {}) if isinstance(dep, Mapping) else {}


def backend(config: Mapping) -> str:
    dep = config.get("delegation") or {}
    return str(dep.get("backend") or "").strip() if isinstance(dep, Mapping) else ""


def routes_from_config(config: Mapping) -> list:
    """model_map 설정에서 등록 경로 목록을 만든다. backend 가 model_map 이 아니면 빈 목록."""
    if backend(config) != BACKEND:
        return []
    out = []
    for entry in _block(config).get("options") or []:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "").strip()
        model = str(entry.get("model") or "").strip()
        if not name or not model:
            continue
        out.append(rules.Route(name, model, entry.get("reasoning_effort"), entry.get("service_tier")))
    return out


def entries_by_name(config: Mapping) -> dict:
    return {str(e.get("name") or "").strip(): e
            for e in (_block(config).get("options") or []) if isinstance(e, Mapping)}


def default_route(config: Mapping) -> str:
    return str(_block(config).get("default") or "").strip()


def task_list(args: Mapping) -> list:
    tasks = args.get("tasks")
    if isinstance(tasks, list):
        return [t for t in tasks if isinstance(t, Mapping)]
    goal = args.get("goal")
    if isinstance(goal, str) and goal.strip():
        return [{"goal": goal, "context": args.get("context")}]
    return []


def _has_images(args: Mapping, task: Mapping) -> bool:
    for holder in (args, task):
        images = holder.get("images")
        if isinstance(images, list) and images:
            return True
    return False


def guard_call(args: Mapping, config: Mapping, caps: Mapping, *, strict: bool = True) -> Optional[str]:
    """차단할 이유가 있으면 메시지를, 없으면 None 을 돌려준다."""
    if not isinstance(args, Mapping):
        return None
    if str(args.get("action") or "").strip().lower() in CONTROL_ACTIONS:
        return None
    routes = routes_from_config(config)
    if not routes:
        return None  # model_map 이 아니면 이 가드는 관여하지 않는다
    tasks = task_list(args)
    if not tasks:
        return None
    names = [r.name for r in routes]
    entries = entries_by_name(config)
    fallback_default = default_route(config)
    blocks = []
    for i, task in enumerate(tasks):
        chosen = str(task.get("option") or "").strip() or fallback_default
        if not chosen:
            blocks.append(f"task {i}: no option given and the default route is empty.")
            continue
        if chosen not in entries:
            blocks.append(f"task {i}: '{chosen}' is not a registered route. Available: {', '.join(names)}")
            continue
        probe = rules.Task(
            id=f"task{i}",
            input_tokens=None,
            needs_modalities=frozenset({"text", "image"} if _has_images(args, task) else {"text"}),
            needs_tools=True,
        )
        decision = rules.evaluate(probe, routes, caps, registered=names)
        reasons = list(decision.rejected.get(chosen) or ())
        entry = entries.get(chosen) or {}
        model = str(entry.get("model") or "").strip()
        c = caps.get(model)
        if c is not None and c.free and entry.get("fallback_providers"):
            reasons.append(FALLBACK_VIOLATION)
        if not reasons:
            continue
        if not strict and set(reasons) == {rules.UNKNOWN_MODEL}:
            logger.warning("routing-guard: %s 의 모델 %s 능력 정보가 없어 통과시킵니다", chosen, model)
            continue
        alternatives = [n for n in decision.eligible if n != chosen]
        if fallback_default in alternatives:  # 기본 경로를 먼저 보여 준다
            alternatives.remove(fallback_default)
            alternatives.insert(0, fallback_default)
        lines = [f"task {i}: route '{chosen}' violates hard rules: {', '.join(reasons)}"]
        if reasons == [rules.UNKNOWN_MODEL]:
            lines.append("  Model is missing from the capability snapshot. Refresh it with `python adapters/hermes/sync_plugin.py`.")
        lines.append("  Alternatives: " + (", ".join(alternatives[:6]) if alternatives
                                   else "none; do the work directly as the parent or change the conditions"))
        blocks.append("\n".join(lines))
    if not blocks:
        return None
    return ("delegate_task blocked by routing hard rules (routing-guard)\n- " + "\n- ".join(blocks)
            + "\nChange the route or do the work directly as the parent. Model recommendations cannot override this verdict.")
