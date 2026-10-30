"""routing-guard: delegate_task 실행 전에 경로 자격을 하드 규칙으로 검사한다.

`pre_tool_call` 훅에서 delegate_task 호출을 가로채, 선택된 경로가 core/eligibility 규칙을
통과하는지 확인하고 위반이면 ``{"action": "block", "message": ...}`` 로 실행을 막는다.
판정 로직은 guard.py(순수 로직)에 있고, 이 파일은 Hermes 연결만 담당한다.

설정은 ``plugins.entries.routing-guard.settings`` 아래에 둔다.
  strict_unknown_model: true   # 능력 정보에 없는 모델도 차단(기본). false 면 경고만 남기고 통과
  capabilities_path: ""        # 비우면 플러그인 폴더의 capabilities.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent
_CAPS = {"mtime": None, "data": {}}


def _load_caps(path: Path):
    """capabilities.json 을 읽어 ModelCaps 로 바꾼다. 파일이 바뀌면 다시 읽는다."""
    from . import eligibility_rules as rules

    mtime = path.stat().st_mtime
    if _CAPS["mtime"] != mtime:
        doc = json.loads(path.read_text(encoding="utf-8"))
        _CAPS["data"] = {m: rules.ModelCaps.from_dict(m, d) for m, d in doc["models"].items()}
        _CAPS["mtime"] = mtime
    return _CAPS["data"]


def register(ctx) -> None:
    from .guard import TOOL, guard_call

    try:
        strict = bool(ctx.get_config("strict_unknown_model", True))
        configured = str(ctx.get_config("capabilities_path", "") or "").strip()
    except Exception:  # 설정 조회가 실패해도 기본값으로 동작한다
        strict, configured = True, ""
    caps_path = Path(configured) if configured else _DIR / "capabilities.json"

    def _caps():
        if caps_path.exists():
            return _load_caps(caps_path)
        return _load_caps(_DIR / "capabilities.json")

    def _pre_tool_call(tool_name, args=None, **kwargs):
        if tool_name != TOOL:
            return None
        try:
            from hermes_cli.config import load_config_readonly

            config = load_config_readonly() or {}
            message = guard_call(args or {}, config, _caps(), strict=strict)
        except Exception:
            # 가드 버그로 모든 위임을 막는 것이 더 위험하므로 통과시키고 크게 남긴다.
            logger.warning("routing-guard: 검사에 실패해 이번 호출을 통과시킵니다", exc_info=True)
            return None
        if message:
            logger.warning("routing-guard: delegate_task 차단\n%s", message)
            return {"action": "block", "message": message}
        return None

    ctx.register_hook("pre_tool_call", _pre_tool_call)
    logger.info("routing-guard 활성 (strict_unknown_model=%s, capabilities=%s)", strict, caps_path)
