#!/usr/bin/env python3
"""Codex PreToolUse 훅 진입점. stdin 의 JSON 을 읽어 spawn_agent 호출을 검사한다. 표준 라이브러리만 사용한다.

종료 코드: 0 = 통과(차단 시에는 stdout 에 deny JSON), 1 = 입력 오류 같은 차단 없는 훅 오류.
훅이 죽거나 시간 초과면 Codex 는 호출을 막지 않는다(fail-open). 이 가드는 안전 장치이지 보안 경계가 아니다.

환경변수 SUBAGENT_ROUTING_UNKNOWN=allow 이면 자격 불명 호출을 통과시킨다. 그 밖의 값은 deny(기본)로 해석한다.
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import guard  # noqa: E402


def codex_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CODEX_HOME") or pathlib.Path.home() / ".codex")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except ValueError as exc:
        print(f"subagent-routing-kit: stdin is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("subagent-routing-kit: stdin JSON is not an object", file=sys.stderr)
        return 1
    if payload.get("hook_event_name") != "PreToolUse":
        return 0
    unknown = guard.UNKNOWN_ALLOW if os.environ.get("SUBAGENT_ROUTING_UNKNOWN", "").strip().lower() == "allow" \
        else guard.UNKNOWN_DENY
    message = guard.check(payload, guard.load_capabilities(), codex_home=codex_home(), unknown=unknown)
    if message:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message,
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
