"""하드 규칙 판정기: 경로의 자격·금지 조건을 코드로 확정한다. 표준 라이브러리만 사용.

신경망 추천이나 부모 판단이 이 판정을 우회하지 못한다. 이 모듈은 특정 에이전트 프레임워크를 모른다.
등록된 경로 목록과 모델 능력은 어댑터와 카탈로그가 주입한다.

판정은 "후보를 거르는 일"까지다. 남은 후보 중 무엇을 고를지, 애매한 건을 어떻게 처리할지는
부모의 몫이다(docs/hybrid-routing-design.md).
"""
from __future__ import annotations

import json
import pathlib
import posixpath
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

# 이 프로젝트에서 실제 지원이 확인된 속도 단계는 normal 뿐이다. 다른 값은 근거와 함께 명시적으로 허용해야 한다.
DEFAULT_SERVICE_TIERS = frozenset({"normal"})

# --- 위반 코드 (상세 값이 붙는 코드는 "코드:값" 형식) -----------------------------------------
ROUTE_NOT_REGISTERED = "route_not_registered"
UNKNOWN_MODEL = "unknown_model"
EFFORT_IMPLICIT = "effort_implicit"
EFFORT_CANNOT_DISABLE = "effort_cannot_disable"
EFFORT_UNADVERTISED = "effort_unadvertised"
SERVICE_TIER_IMPLICIT = "service_tier_implicit"
SERVICE_TIER_UNVERIFIED = "service_tier_unverified"
FREE_TO_PAID_FALLBACK = "free_to_paid_fallback"
MODALITY_UNSUPPORTED = "modality_unsupported"
TOOLS_UNSUPPORTED = "tools_unsupported"
CONTEXT_EXCEEDED = "context_exceeded"
LONG_CONTEXT_SURCHARGE = "long_context_surcharge"
# --- 경고 코드 (거부하지 않고 부모에게 알린다) ----------------------------------------------
WARN_LENGTH_UNKNOWN = "input_length_unknown_surcharge_risk"
# --- 결정 상태 ---------------------------------------------------------------------------
ELIGIBLE = "eligible"
NEEDS_PARENT = "needs_parent"
NEEDS_APPROVAL = "needs_approval"


@dataclass(frozen=True)
class ModelCaps:
    model: str
    context_tokens: Optional[int]
    input_modalities: frozenset
    supports_tools: bool
    supports_reasoning: bool
    reasoning_mandatory: bool
    supported_efforts: Optional[tuple]  # None = 강도 선택 목록 미공개
    long_context_surcharge_tokens: Optional[int]
    free: bool

    @classmethod
    def from_dict(cls, model: str, d: Mapping) -> "ModelCaps":
        efforts = d.get("supported_efforts")
        return cls(
            model=model,
            context_tokens=d.get("context_tokens"),
            input_modalities=frozenset(d.get("input_modalities") or ()),
            supports_tools=bool(d.get("supports_tools")),
            supports_reasoning=bool(d.get("supports_reasoning")),
            reasoning_mandatory=bool(d.get("reasoning_mandatory")),
            supported_efforts=tuple(efforts) if isinstance(efforts, list) else None,
            long_context_surcharge_tokens=d.get("long_context_surcharge_tokens"),
            free=bool(d.get("free")),
        )


@dataclass(frozen=True)
class Route:
    """부모가 호출할 수 있게 등록된 모델·추론 강도·속도 조합."""
    name: str
    model: str
    reasoning_effort: Optional[str]  # None = 명시하지 않음(상속). 이 정책은 명시를 요구한다
    service_tier: Optional[str]
    fallback_routes: tuple = ()  # 실패 시 넘어가는 경로 이름


@dataclass(frozen=True)
class Task:
    id: str
    input_tokens: Optional[int] = None  # None = 모름
    needs_modalities: frozenset = frozenset({"text"})
    needs_tools: bool = False
    allow_long_context_surcharge: bool = False
    requires_approval: bool = False
    approved: bool = False
    high_risk: bool = False
    write_scope: tuple = ()


@dataclass(frozen=True)
class Decision:
    task_id: str
    status: str
    eligible: tuple
    rejected: Mapping  # 경로 이름 -> 위반 코드 튜플
    warnings: Mapping  # 경로 이름 -> 경고 코드 튜플
    flags: tuple  # 예: independent_review


def load_capabilities(path) -> dict:
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return {m: ModelCaps.from_dict(m, d) for m, d in doc["models"].items()}


def routes_from_specs(path) -> list:
    """variant-specs.json 형식의 명세를 Route 목록으로 바꾼다. 폴백은 없다."""
    specs = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return [Route(s["name"], s["model"], s.get("reasoning_effort"), s.get("service_tier")) for s in specs]


def route_violations(route: Route, caps: Mapping, routes_by_name: Mapping,
                     allowed_service_tiers: Iterable = DEFAULT_SERVICE_TIERS) -> list:
    """작업과 무관하게 경로 자체가 위반하는 규칙."""
    c = caps.get(route.model)
    if c is None:
        return [UNKNOWN_MODEL]
    out = []
    e = route.reasoning_effort
    if e is None:
        out.append(EFFORT_IMPLICIT)
    elif e == "none":
        if c.reasoning_mandatory or not c.supports_reasoning:
            out.append(EFFORT_CANNOT_DISABLE)
    elif c.supported_efforts is None or e not in c.supported_efforts:
        out.append(EFFORT_UNADVERTISED)
    if route.service_tier is None:
        out.append(SERVICE_TIER_IMPLICIT)
    elif route.service_tier not in set(allowed_service_tiers):
        out.append(SERVICE_TIER_UNVERIFIED)
    if c.free:
        for fb in route.fallback_routes:
            target = routes_by_name.get(fb)
            tc = caps.get(target.model) if target else None
            if tc is None or not tc.free:  # 알 수 없는 폴백도 유료로 간주한다
                out.append(FREE_TO_PAID_FALLBACK)
                break
    return out


def task_violations(task: Task, route: Route, caps: Mapping):
    """작업 조건과 경로의 충돌. (위반 목록, 경고 목록)을 돌려준다."""
    c = caps.get(route.model)
    if c is None:
        return [], []
    out, warn = [], []
    for m in sorted(task.needs_modalities - c.input_modalities):
        out.append(f"{MODALITY_UNSUPPORTED}:{m}")
    if task.needs_tools and not c.supports_tools:
        out.append(TOOLS_UNSUPPORTED)
    n = task.input_tokens
    if n is not None and c.context_tokens is not None and n > c.context_tokens:
        out.append(CONTEXT_EXCEEDED)
    t = c.long_context_surcharge_tokens
    if t is not None:
        if n is None:
            warn.append(WARN_LENGTH_UNKNOWN)
        elif n >= t and not task.allow_long_context_surcharge:
            out.append(LONG_CONTEXT_SURCHARGE)
    return out, warn


def evaluate(task: Task, routes: Iterable, caps: Mapping, *, registered: Iterable,
             allowed_service_tiers: Iterable = DEFAULT_SERVICE_TIERS) -> Decision:
    """후보 경로를 하드 규칙으로 거른다. registered 는 어댑터가 알려 주는 현재 등록된 경로 이름이다."""
    routes = list(routes)
    registered = set(registered)
    by_name = {r.name: r for r in routes}
    eligible, rejected, warnings = [], {}, {}
    for r in routes:
        reasons = [] if r.name in registered else [ROUTE_NOT_REGISTERED]
        reasons += route_violations(r, caps, by_name, allowed_service_tiers)
        t_out, t_warn = task_violations(task, r, caps)
        reasons += t_out
        if t_warn:
            warnings[r.name] = tuple(t_warn)
        if reasons:
            rejected[r.name] = tuple(reasons)
        else:
            eligible.append(r.name)
    # 위험 신호는 검토를 추가할 뿐 어떤 규칙도 해제하지 않는다.
    flags = ("independent_review",) if task.high_risk else ()
    if task.requires_approval and not task.approved:
        status = NEEDS_APPROVAL
    elif not eligible:
        status = NEEDS_PARENT
    else:
        status = ELIGIBLE
    return Decision(task.id, status, tuple(eligible), rejected, warnings, flags)


def _parts(path: str) -> tuple:
    """경로를 정규화해 구성 요소로 나눈다. 저장소 전체('.', '/')는 빈 튜플이며 모든 경로와 겹친다."""
    p = posixpath.normpath(path.replace("\\", "/"))
    return tuple(x for x in p.split("/") if x not in ("", "."))


def scopes_overlap(a: Iterable, b: Iterable) -> bool:
    """쓰기 범위가 겹치는지. 같은 경로이거나 한쪽이 다른 쪽의 상위 디렉터리면 겹친다.

    범위가 비어 있으면(쓰기 없음) 겹치지 않는다. 경로는 같은 기준 디렉터리에 대한 상대 경로로 통일해서 넘긴다.
    """
    pa = [_parts(x) for x in a]
    pb = [_parts(x) for x in b]
    if not pa or not pb:
        return False
    for x in pa:
        for y in pb:
            n = min(len(x), len(y))
            if x[:n] == y[:n]:
                return True
    return False


def plan_write_stages(tasks: Iterable) -> list:
    """쓰기 범위가 겹치는 작업을 서로 다른 단계로 나눈다. 같은 단계의 작업은 병렬로 실행해도 된다.

    쓰기 범위가 비어 있는 작업은 충돌하지 않는다. 입력 순서를 보존해 결과가 결정적이다.
    """
    stages: list = []
    for t in tasks:
        for stage in stages:
            if not any(scopes_overlap(t.write_scope, o.write_scope) for o in stage):
                stage.append(t)
                break
        else:
            stages.append([t])
    return [[t.id for t in stage] for stage in stages]
