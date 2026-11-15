"""Codex 어댑터의 PreToolUse 훅 로직과 진입점 테스트.

플러그인은 이 저장소의 의존성이 없는 환경에서 돌아가므로 표준 라이브러리만으로 실행한다:
  python3 -m unittest tests.test_codex_routing_guard
Codex 를 띄우지 않는다. 실제 Codex 설치·훅 발동은 tests/test_codex_plugin_package.py 의 선택 검사와 README 에 구분해 적는다.
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "adapters" / "codex" / "marketplace" / "plugins" / "subagent-routing-kit"
SCRIPTS = PLUGIN / "scripts"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PluginModules:
    """설치된 모양 그대로(scripts/ 가 sys.path 에 있는 상태) 플러그인 모듈을 불러온다."""

    def __enter__(self):
        self._path = list(sys.path)
        sys.path.insert(0, str(SCRIPTS))
        self.rules = _load("eligibility_rules", SCRIPTS / "eligibility_rules.py")
        self.guard = _load("guard", SCRIPTS / "guard.py")
        return self

    def __exit__(self, *exc):
        sys.path[:] = self._path
        for name in ("eligibility_rules", "guard"):
            sys.modules.pop(name, None)


def write_role(directory, name, model=None, effort=None, filename=None):
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lines = [f'name = "{name}"', 'description = "d"']
    if model:
        lines.append(f'model = "{model}"')
    if effort:
        lines.append(f'model_reasoning_effort = "{effort}"')
    lines.append('developer_instructions = "x"')
    (directory / (filename or f"{name}.toml")).write_text("\n".join(lines) + "\n", encoding="utf-8")


def payload(tool_input, *, tool_name="spawn_agent", cwd="/nowhere", **extra):
    return {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input,
            "cwd": cwd, "model": "gpt-6-sol", "session_id": "s", "turn_id": "t",
            "tool_use_id": "u", "permission_mode": "default", "transcript_path": None, **extra}


class GuardLogicTest(unittest.TestCase):
    def setUp(self):
        self.mods = PluginModules().__enter__()
        self.addCleanup(self.mods.__exit__)
        self.guard = self.mods.guard
        self.caps = self.guard.load_capabilities()
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.home = self.tmp / "codex_home"
        self.project = self.tmp / "proj"
        (self.project / ".git").mkdir(parents=True)

    def check(self, tool_input, unknown="deny", **kw):
        kw.setdefault("cwd", str(self.project))
        return self.guard.check(payload(tool_input, **kw), self.caps, codex_home=self.home, unknown=unknown)

    # --- 도구 이름 -----------------------------------------------------------------------------
    def test_tool_names_v1_v2_and_alias(self):
        for name in ("spawn_agent", "collaborationspawn_agent", "collaboration.spawn_agent", "Agent"):
            self.assertTrue(self.guard.is_spawn_tool(name), name)
        for name in ("Bash", "send_message", "wait_agent", "close_agent", "", None):
            self.assertFalse(self.guard.is_spawn_tool(name), name)

    def test_other_tool_is_ignored(self):
        self.assertIsNone(self.guard.check(payload({"command": "ls"}, tool_name="Bash"), self.caps,
                                           codex_home=self.home))

    # --- 호출 인자만으로 판정되는 경우 ------------------------------------------------------------
    def test_explicit_supported_model_and_effort_pass(self):
        self.assertIsNone(self.check({"task_name": "a", "message": "m", "model": "gpt-6-luna",
                                      "reasoning_effort": "high"}))

    def test_v1_payload_shape_passes(self):
        self.assertIsNone(self.check({"message": "m", "fork_context": False, "model": "gpt-6-luna",
                                      "reasoning_effort": "low"}))

    def test_tool_input_given_as_json_string(self):
        raw = json.dumps({"message": "m", "model": "nope-9", "reasoning_effort": "low"})
        self.assertIn("unknown_model", self.check(raw))

    def test_unknown_model_blocked_even_when_unknown_policy_allows(self):
        msg = self.check({"message": "m", "model": "nope-9", "reasoning_effort": "low"}, unknown="allow")
        self.assertIn("unknown_model", msg)
        self.assertIn("nope-9", msg)

    def test_effort_not_advertised_for_that_model(self):
        # gpt-6-luna 은 ultra 를 광고하지 않는다(gpt-6-sol 은 광고함)
        self.assertIn("effort_unadvertised", self.check({"message": "m", "model": "gpt-6-luna",
                                                         "reasoning_effort": "ultra"}))
        self.assertIsNone(self.check({"message": "m", "model": "gpt-6-sol", "reasoning_effort": "ultra"}))

    def test_effort_none_is_rejected_because_catalog_has_no_off_level(self):
        self.assertIn("effort_cannot_disable", self.check({"message": "m", "model": "gpt-6-luna",
                                                           "reasoning_effort": "none"}))

    def test_image_items_need_image_modality(self):
        caps = dict(self.caps)
        caps["text-only"] = self.mods.rules.ModelCaps.from_dict("text-only", {
            "context_tokens": 1000, "input_modalities": ["text"], "supports_tools": True,
            "supports_reasoning": True, "reasoning_mandatory": True, "supported_efforts": ["low"]})
        ti = {"items": [{"type": "text", "text": "x"}, {"type": "image", "image_url": "u"}],
              "model": "text-only", "reasoning_effort": "low"}
        msg = self.guard.check(payload(ti), caps, codex_home=self.home)
        self.assertIn("modality_unsupported:image", msg)
        ti["items"] = [{"type": "text", "text": "x"}]
        self.assertIsNone(self.guard.check(payload(ti), caps, codex_home=self.home))

    # --- 자격 불명 -------------------------------------------------------------------------------
    def test_omitted_model_and_effort_is_unknown_and_denied_by_default(self):
        msg = self.check({"message": "m"})
        self.assertIn("eligibility unknown", msg)
        self.assertIn("model", msg)
        self.assertIn("reasoning_effort", msg)

    def test_unknown_policy_allow_passes_unknown_but_not_violations(self):
        self.assertIsNone(self.check({"message": "m"}, unknown="allow"))
        self.assertIsNone(self.check({"message": "m", "model": "gpt-6-luna"}, unknown="allow"))

    def test_omitted_effort_alone_is_unknown(self):
        self.assertIn("eligibility unknown", self.check({"message": "m", "model": "gpt-6-luna"}))

    def test_unknown_message_never_claims_final_model(self):
        msg = self.check({"message": "m"})
        self.assertNotIn("will run", msg)
        self.assertIn("cannot be determined", msg)

    # --- 사용자 정의 에이전트(role) -----------------------------------------------------------------
    def test_project_role_with_model_and_effort_passes(self):
        write_role(self.project / ".codex" / "agents", "scout", "gpt-6-luna", "medium")
        self.assertIsNone(self.check({"message": "m", "agent_type": "scout"}))

    def test_role_name_comes_from_name_field_not_filename(self):
        write_role(self.project / ".codex" / "agents", "scout", "gpt-6-luna", "medium", filename="whatever.toml")
        self.assertIsNone(self.check({"message": "m", "agent_type": "scout"}))

    def test_role_with_ineligible_model_is_blocked(self):
        write_role(self.project / ".codex" / "agents", "scout", "nope-9", "low")
        self.assertIn("unknown_model", self.check({"message": "m", "agent_type": "scout"}))

    def test_role_may_override_call_values_so_both_are_checked(self):
        write_role(self.project / ".codex" / "agents", "scout", "nope-9", "low")
        msg = self.check({"message": "m", "agent_type": "scout", "model": "gpt-6-luna",
                          "reasoning_effort": "high"})
        self.assertIn("unknown_model", msg)
        self.assertIn("custom agent", msg)

    def test_call_values_fill_what_the_role_leaves_out(self):
        write_role(self.project / ".codex" / "agents", "scout", "gpt-6-luna")
        self.assertIsNone(self.check({"message": "m", "agent_type": "scout", "reasoning_effort": "low"}))

    def test_role_missing_effort_and_call_missing_effort_is_unknown(self):
        write_role(self.project / ".codex" / "agents", "scout", "gpt-6-luna")
        self.assertIn("eligibility unknown", self.check({"message": "m", "agent_type": "scout"}))

    def test_unresolved_agent_type_is_unknown_even_with_explicit_values(self):
        for name in ("explorer", "worker", "missing"):
            msg = self.check({"message": "m", "agent_type": name, "model": "gpt-6-luna",
                              "reasoning_effort": "low"})
            self.assertIn("eligibility unknown", msg, name)
            self.assertIn(name, msg)

    def test_user_level_role_found_in_codex_home(self):
        write_role(self.home / "agents", "scout", "gpt-6-luna", "low")
        self.assertIsNone(self.check({"message": "m", "agent_type": "scout"}))

    def test_project_role_wins_over_user_role_of_same_name(self):
        write_role(self.home / "agents", "scout", "gpt-6-luna", "low")
        write_role(self.project / ".codex" / "agents", "scout", "nope-9", "low")
        self.assertIn("unknown_model", self.check({"message": "m", "agent_type": "scout"}))

    def test_role_found_from_nested_cwd(self):
        write_role(self.project / ".codex" / "agents", "scout", "gpt-6-luna", "low")
        nested = self.project / "a" / "b"
        nested.mkdir(parents=True)
        self.assertIsNone(self.check({"message": "m", "agent_type": "scout"}, cwd=str(nested)))

    def test_invalid_toml_role_is_unresolved_not_a_crash(self):
        d = self.project / ".codex" / "agents"
        d.mkdir(parents=True)
        (d / "scout.toml").write_text("name = [unterminated", encoding="utf-8")
        msg = self.check({"message": "m", "agent_type": "scout", "model": "gpt-6-luna",
                          "reasoning_effort": "low"})
        self.assertIn("eligibility unknown", msg)

    def test_search_stops_at_git_root(self):
        write_role(self.tmp / ".codex" / "agents", "scout", "gpt-6-luna", "low")  # 저장소 밖
        self.assertIn("eligibility unknown", self.check({"message": "m", "agent_type": "scout"}))

    # --- 스냅샷 ---------------------------------------------------------------------------------
    def test_snapshot_records_source_and_covers_listed_models(self):
        doc = json.loads((SCRIPTS / "capabilities.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["source"]["codex_version"], "0.169.0")
        self.assertIn("gpt-6-luna", self.caps)
        self.assertNotIn("gpt-5.1-codex-max", self.caps)  # 이 CLI 버전의 번들 카탈로그에 없다


class HookEntrypointTest(unittest.TestCase):
    """훅을 실제 자식 프로세스로 돌려 stdin/stdout/종료 코드를 확인한다."""

    def run_hook(self, stdin, env_extra=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("SUBAGENT_ROUTING")}
        env["CODEX_HOME"] = tempfile.mkdtemp()
        env.update(env_extra or {})
        return subprocess.run([sys.executable, str(SCRIPTS / "guard_hook.py")], input=stdin,
                              capture_output=True, text=True, env=env, timeout=30)

    def test_violation_emits_documented_deny_json(self):
        p = payload({"message": "m", "model": "nope-9", "reasoning_effort": "low"})
        r = self.run_hook(json.dumps(p))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        spec = out["hookSpecificOutput"]
        self.assertEqual(spec["hookEventName"], "PreToolUse")
        self.assertEqual(spec["permissionDecision"], "deny")
        self.assertIn("unknown_model", spec["permissionDecisionReason"])

    def test_eligible_call_is_silent(self):
        p = payload({"message": "m", "model": "gpt-6-luna", "reasoning_effort": "low"})
        r = self.run_hook(json.dumps(p))
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_unknown_policy_env(self):
        p = json.dumps(payload({"message": "m"}))
        self.assertEqual(json.loads(self.run_hook(p).stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        r = self.run_hook(p, {"SUBAGENT_ROUTING_UNKNOWN": "allow"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        # 알 수 없는 값은 더 엄격한 쪽(deny)으로 해석한다
        r = self.run_hook(p, {"SUBAGENT_ROUTING_UNKNOWN": "maybe"})
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_non_spawn_tool_and_other_events_are_silent(self):
        for p in (payload({"command": "ls"}, tool_name="Bash"),
                  {**payload({}), "hook_event_name": "PostToolUse"}):
            r = self.run_hook(json.dumps(p))
            self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_malformed_stdin_is_a_non_blocking_error(self):
        for bad in ("", "not json", "[]"):
            r = self.run_hook(bad)
            self.assertEqual(r.returncode, 1, bad)  # Codex 는 0/2 이외 종료 코드를 차단 없는 오류로 다룬다
            self.assertEqual(r.stdout, "")
            self.assertTrue(r.stderr.strip())


if __name__ == "__main__":
    unittest.main()
