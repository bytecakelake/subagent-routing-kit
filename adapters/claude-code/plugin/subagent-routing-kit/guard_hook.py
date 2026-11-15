#!/usr/bin/env python3
"""PreToolUse hook entrypoint for the subagent-routing-kit Claude Code plugin.

Reads the hook's JSON from stdin, checks an `Agent`/`Task` call with guard.py,
and writes a decision JSON to stdout. Always exits 0: Claude Code reads
`hookSpecificOutput.permissionDecision`, not the exit code, for this event, and
a bug here must fail open (silently allow) rather than block every delegation.

Configuration is via environment variables, since a bare "command" hook has no
Hermes-style settings object:
  ROUTING_GUARD_STRICT_UNKNOWN_MODEL   "false" to warn instead of block on an
                                        unknown model (default: strict/block)
  ROUTING_GUARD_CAPABILITIES_PATH      override for capabilities.json
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Optional

_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR))

import eligibility_rules as rules  # noqa: E402
import guard  # noqa: E402


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "")


def _load_caps(path: pathlib.Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {m: rules.ModelCaps.from_dict(m, d) for m, d in doc["models"].items()}


def run(payload: dict, env: dict) -> Optional[dict]:
    """Pure wrapper around guard.guard_call for testing without real stdin/env."""
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    project_dir = env.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    home_dir = env.get("HOME") or env.get("USERPROFILE") or ""
    agents = guard.discover_agents(guard.agent_search_dirs(project_dir, home_dir))
    caps_path = pathlib.Path(env.get("ROUTING_GUARD_CAPABILITIES_PATH") or (_DIR / "capabilities.json"))
    caps = _load_caps(caps_path)
    strict = _bool_env("ROUTING_GUARD_STRICT_UNKNOWN_MODEL", True) if "ROUTING_GUARD_STRICT_UNKNOWN_MODEL" not in env \
        else env["ROUTING_GUARD_STRICT_UNKNOWN_MODEL"].strip().lower() not in ("0", "false", "no", "")
    message = guard.guard_call(tool_name, tool_input, agents, caps, strict=strict)
    if not message:
        return None
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": message,
    }}


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0  # malformed input: fail open rather than guess
    try:
        output = run(payload, dict(os.environ))
    except Exception as exc:  # a guard bug must not block every delegation
        print(f"subagent-routing-kit: guard check failed, allowing the call: {exc}", file=sys.stderr)
        return 0
    if output:
        print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
