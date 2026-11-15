"""Unit tests for the Claude Code routing-guard adapter (pure logic + hook entrypoint).

Run with plain python3 (no deps) — this mirrors the plugin's own runtime, which has none
of this repo's dependencies installed:
  python3 -m unittest tests.test_claude_code_routing_guard
"""
import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "adapters" / "claude-code" / "plugin" / "subagent-routing-kit"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _PluginModules:
    """Load the plugin's own module copies exactly as installed, with PLUGIN on sys.path
    so their internal `import eligibility_rules` / `import agent_frontmatter` resolve."""

    def __enter__(self):
        self._saved_path = list(sys.path)
        sys.path.insert(0, str(PLUGIN))
        self.rules = _load("eligibility_rules", PLUGIN / "eligibility_rules.py")
        self.frontmatter = _load("agent_frontmatter", PLUGIN / "agent_frontmatter.py")
        self.guard = _load("guard", PLUGIN / "guard.py")
        self.guard_hook = _load("guard_hook", PLUGIN / "guard_hook.py")
        return self

    def __exit__(self, *exc):
        sys.path[:] = self._saved_path
        for name in ("eligibility_rules", "agent_frontmatter", "guard", "guard_hook"):
            sys.modules.pop(name, None)


def write_agent(dir_path: pathlib.Path, name: str, model: str = None, description: str = "d"):
    dir_path.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {name}", f"description: {description}"]
    if model:
        lines.append(f"model: {model}")
    lines.append("---")
    lines.append("You are a subagent.")
    (dir_path / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")


class FrontmatterTest(unittest.TestCase):
    def test_parses_scalar_fields(self):
        with _PluginModules() as m:
            meta = m.frontmatter.parse_frontmatter(
                "---\nname: code-reviewer\ndescription: Reviews code\nmodel: sonnet\n---\nbody")
            self.assertEqual(meta["name"], "code-reviewer")
            self.assertEqual(meta["model"], "sonnet")

    def test_no_fence_returns_empty(self):
        with _PluginModules() as m:
            self.assertEqual(m.frontmatter.parse_frontmatter("no frontmatter here"), {})

    def test_missing_name_is_skipped_by_read_agent_file(self):
        with _PluginModules() as m, tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "x.md"
            path.write_text("---\ndescription: no name\n---\nbody", encoding="utf-8")
            self.assertIsNone(m.frontmatter.read_agent_file(path))

    def test_omitted_model_is_none(self):
        with _PluginModules() as m, tempfile.TemporaryDirectory() as d:
            write_agent(pathlib.Path(d), "reviewer")
            agent = m.frontmatter.read_agent_file(pathlib.Path(d) / "reviewer.md")
            self.assertIsNone(agent["model"])


class GuardCallTest(unittest.TestCase):
    def setUp(self):
        self._ctx = _PluginModules()
        self.m = self._ctx.__enter__()
        self.caps = self.m.rules.load_capabilities(ROOT / "adapters" / "claude-code" / "model-capabilities.json")

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def test_registered_route_with_known_model_passes(self):
        agents = {"reviewer": {"name": "reviewer", "model": "sonnet"}}
        msg = self.m.guard.guard_call("Agent", {"subagent_type": "reviewer"}, agents, self.caps)
        self.assertIsNone(msg)

    def test_task_alias_also_checked(self):
        agents = {"reviewer": {"name": "reviewer", "model": "sonnet"}}
        msg = self.m.guard.guard_call("Task", {"subagent_type": "reviewer"}, agents, self.caps)
        self.assertIsNone(msg)

    def test_other_tool_is_ignored(self):
        msg = self.m.guard.guard_call("Read", {"path": "a"}, {}, self.caps)
        self.assertIsNone(msg)

    def test_unregistered_subagent_is_blocked(self):
        msg = self.m.guard.guard_call("Agent", {"subagent_type": "ghost"}, {}, self.caps)
        self.assertIsNotNone(msg)
        self.assertIn(self.m.rules.ROUTE_NOT_REGISTERED, msg)

    def test_unknown_model_is_blocked_in_strict_mode(self):
        agents = {"reviewer": {"name": "reviewer", "model": "gpt-9-made-up"}}
        msg = self.m.guard.guard_call("Agent", {"subagent_type": "reviewer"}, agents, self.caps, strict=True)
        self.assertIsNotNone(msg)
        self.assertIn(self.m.rules.UNKNOWN_MODEL, msg)

    def test_unknown_model_passes_in_non_strict_mode(self):
        agents = {"reviewer": {"name": "reviewer", "model": "gpt-9-made-up"}}
        msg = self.m.guard.guard_call("Agent", {"subagent_type": "reviewer"}, agents, self.caps, strict=False)
        self.assertIsNone(msg)

    def test_omitted_model_inherits_and_is_unknown(self):
        agents = {"reviewer": {"name": "reviewer", "model": None}}
        msg = self.m.guard.guard_call("Agent", {"subagent_type": "reviewer"}, agents, self.caps)
        self.assertIsNotNone(msg)
        self.assertIn(self.m.guard.INHERIT_MODEL, msg)

    def test_per_call_model_override_beats_agent_file_model(self):
        agents = {"reviewer": {"name": "reviewer", "model": "haiku"}}
        # override to an unknown model must be what gets checked, not the file's "haiku"
        msg = self.m.guard.guard_call(
            "Agent", {"subagent_type": "reviewer", "model": "unknown-model-x"}, agents, self.caps)
        self.assertIsNotNone(msg)
        self.assertIn(self.m.rules.UNKNOWN_MODEL, msg)

    def test_effort_axis_never_blocks(self):
        # Every route has reasoning_effort=None; the adapter must filter EFFORT_IMPLICIT etc.
        agents = {"reviewer": {"name": "reviewer", "model": "opus"}}
        msg = self.m.guard.guard_call("Agent", {"subagent_type": "reviewer"}, agents, self.caps)
        self.assertIsNone(msg)

    def test_alternatives_are_listed_on_block(self):
        agents = {
            "reviewer": {"name": "reviewer", "model": "gpt-9-made-up"},
            "debugger": {"name": "debugger", "model": "sonnet"},
        }
        msg = self.m.guard.guard_call("Agent", {"subagent_type": "reviewer"}, agents, self.caps)
        self.assertIn("debugger", msg)


class DiscoverAgentsTest(unittest.TestCase):
    def test_discovers_project_and_user_dirs_project_wins(self):
        with _PluginModules() as m, tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            write_agent(root / "project" / ".claude" / "agents", "reviewer", model="sonnet")
            write_agent(root / "home" / ".claude" / "agents", "reviewer", model="haiku")
            write_agent(root / "home" / ".claude" / "agents", "debugger", model="opus")
            dirs = m.guard.agent_search_dirs(str(root / "project"), str(root / "home"))
            agents = m.guard.discover_agents(dirs)
            self.assertEqual(agents["reviewer"]["model"], "sonnet")  # project wins
            self.assertEqual(agents["debugger"]["model"], "opus")   # user-only agent still found


class HookEntrypointTest(unittest.TestCase):
    """Exercises guard_hook.run() exactly as guard_hook.main() would, without real stdin/env."""

    def setUp(self):
        self._ctx = _PluginModules()
        self.m = self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def test_allowed_call_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            write_agent(root / ".claude" / "agents", "reviewer", model="sonnet")
            out = self.m.guard_hook.run(
                {"tool_name": "Agent", "tool_input": {"subagent_type": "reviewer"}},
                {"CLAUDE_PROJECT_DIR": str(root), "HOME": str(root / "no-home")})
            self.assertIsNone(out)

    def test_blocked_call_returns_deny_decision(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            out = self.m.guard_hook.run(
                {"tool_name": "Agent", "tool_input": {"subagent_type": "ghost"}},
                {"CLAUDE_PROJECT_DIR": str(root), "HOME": str(root / "no-home")})
            self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn("ghost", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_malformed_stdin_fails_open_via_main(self):
        """main() reads real stdin; simulate it directly to prove the fail-open path."""
        import io
        with _PluginModules() as m:
            old_stdin = sys.stdin
            sys.stdin = io.StringIO("not json")
            try:
                self.assertEqual(m.guard_hook.main(), 0)
            finally:
                sys.stdin = old_stdin


if __name__ == "__main__":
    unittest.main()
