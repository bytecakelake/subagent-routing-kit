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

    def test_undiscoverable_subagent_is_not_blocked_as_unregistered(self):
        # Built-in, managed, --agents CLI and plugin agents have no file this hook can scan.
        for name in ("Explore", "Plan", "general-purpose", "statusline-setup", "claude-code-guide",
                     "my-plugin:reviewer", "ghost"):
            self.assertIsNone(self.m.guard.guard_call("Agent", {"subagent_type": name}, {}, self.caps), name)

    def test_undiscoverable_subagent_with_unknown_model_override_is_blocked(self):
        msg = self.m.guard.guard_call(
            "Agent", {"subagent_type": "Explore", "model": "gpt-9-made-up"}, {}, self.caps)
        self.assertIn(self.m.rules.UNKNOWN_MODEL, msg)

    def test_undiscoverable_subagent_with_known_model_override_passes(self):
        self.assertIsNone(self.m.guard.guard_call(
            "Agent", {"subagent_type": "Explore", "model": "haiku"}, {}, self.caps))

    def test_never_reports_route_not_registered(self):
        msg = self.m.guard.guard_call(
            "Agent", {"subagent_type": "ghost", "model": "nope"}, {}, self.caps)
        self.assertNotIn(self.m.rules.ROUTE_NOT_REGISTERED, msg)

    def test_unknown_model_is_blocked_in_strict_mode(self):
        agents = {"reviewer": {"name": "reviewer", "model": "gpt-9-made-up"}}
        msg = self.m.guard.guard_call("Agent", {"subagent_type": "reviewer"}, agents, self.caps, strict=True)
        self.assertIsNotNone(msg)
        self.assertIn(self.m.rules.UNKNOWN_MODEL, msg)

    def test_unknown_model_passes_in_non_strict_mode(self):
        agents = {"reviewer": {"name": "reviewer", "model": "gpt-9-made-up"}}
        msg = self.m.guard.guard_call("Agent", {"subagent_type": "reviewer"}, agents, self.caps, strict=False)
        self.assertIsNone(msg)

    def test_omitted_or_inherit_model_is_unobservable_and_passes(self):
        # The effective model depends on the session, CLAUDE_CODE_SUBAGENT_MODEL and the provider;
        # the hook cannot see any of them, so it must not invent one and block.
        for model in (None, "inherit"):
            agents = {"reviewer": {"name": "reviewer", "model": model}}
            self.assertIsNone(self.m.guard.guard_call(
                "Agent", {"subagent_type": "reviewer"}, agents, self.caps), model)

    def test_per_call_override_is_checked_even_when_agent_inherits(self):
        agents = {"reviewer": {"name": "reviewer", "model": None}}
        msg = self.m.guard.guard_call(
            "Agent", {"subagent_type": "reviewer", "model": "nope-x"}, agents, self.caps)
        self.assertIn(self.m.rules.UNKNOWN_MODEL, msg)

    def test_agent_effort_supported_by_model_passes(self):
        for effort in ("low", "medium", "high", "xhigh", "max"):
            agents = {"r": {"name": "r", "model": "sonnet", "effort": effort}}
            self.assertIsNone(self.m.guard.guard_call("Agent", {"subagent_type": "r"}, agents, self.caps))

    def test_agent_effort_unadvertised_is_blocked(self):
        agents = {"r": {"name": "r", "model": "sonnet", "effort": "ultra"}}
        msg = self.m.guard.guard_call("Agent", {"subagent_type": "r"}, agents, self.caps)
        self.assertIn(self.m.rules.EFFORT_UNADVERTISED, msg)

    def test_per_call_effort_overrides_agent_effort(self):
        agents = {"r": {"name": "r", "model": "sonnet", "effort": "max"}}
        msg = self.m.guard.guard_call(
            "Agent", {"subagent_type": "r", "effort": "ultra"}, agents, self.caps)
        self.assertIn(self.m.rules.EFFORT_UNADVERTISED, msg)
        self.assertIsNone(self.m.guard.guard_call(
            "Agent", {"subagent_type": "r", "effort": "low"}, agents, self.caps))

    def test_missing_effort_is_not_blocked(self):
        # Falls back to the session /effort; deliberately not required by this adapter.
        agents = {"r": {"name": "r", "model": "sonnet"}}
        self.assertIsNone(self.m.guard.guard_call("Agent", {"subagent_type": "r"}, agents, self.caps))

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


class StrictFrontmatterTest(unittest.TestCase):
    def read(self, text):
        with _PluginModules() as m, tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "a.md"
            path.write_text(text, encoding="utf-8")
            return m.frontmatter.read_agent_file(path)

    def test_effort_is_read(self):
        a = self.read("---\nname: r\ndescription: d\nmodel: opus\neffort: max\n---\nbody")
        self.assertEqual((a["model"], a["effort"]), ("opus", "max"))

    def test_plain_scalar_with_colon_space_is_accepted(self):
        # Measured: `claude plugin validate .claude/agents` (2.1.325) accepts this.
        a = self.read("---\nname: r\ndescription: Use when: reviewing\n---\nb")
        self.assertEqual(a["description"], "Use when: reviewing")

    def test_stray_non_mapping_line_is_skipped(self):
        # Measured: the real parser rejects this ("YAML Parse error: Unexpected token").
        self.assertIsNone(self.read("---\nname: r\ndescription: d\nfoo bar\n---\nb"))

    def test_unclosed_flow_list_and_leading_at_are_accepted(self):
        # Measured: both pass `claude plugin validate` on 2.1.325, so they are not guessed to be errors.
        self.assertEqual(self.read("---\nname: r\ndescription: d\ntools: [Read, Grep\n---\nb")["name"], "r")
        self.assertEqual(self.read("---\nname: r\ndescription: @x\n---\nb")["name"], "r")

    def test_quoted_colon_is_fine(self):
        self.assertEqual(self.read('---\nname: r\ndescription: "Use when: reviewing"\n---\nb')["name"], "r")

    def test_unterminated_quote_is_skipped(self):
        self.assertIsNone(self.read('---\nname: r\ndescription: "oops\n---\nb'))

    def test_missing_closing_fence_is_skipped(self):
        self.assertIsNone(self.read("---\nname: r\ndescription: d\nbody"))

    def test_tab_indentation_is_skipped(self):
        self.assertIsNone(self.read("---\nname: r\ndescription: d\n\tmodel: opus\n---\nb"))

    def test_block_scalar_description_and_list_tools_parse(self):
        a = self.read("---\nname: r\ndescription: >\n  line one\n  line two\ntools:\n  - Read\n  - Grep\nmodel: haiku # cheap\n---\nb")
        self.assertEqual(a["name"], "r")
        self.assertEqual(a["model"], "haiku")

    def test_flow_list_and_comments_parse(self):
        a = self.read("---\n# c\nname: r\ndescription: d\ntools: [Read, Grep]\n---\nb")
        self.assertEqual(a["name"], "r")

    def test_missing_description_is_skipped(self):
        self.assertIsNone(self.read("---\nname: r\n---\nb"))

    def test_invalid_names_are_skipped(self):
        self.assertIsNone(self.read("---\nname: my:plugin\ndescription: d\n---\nb"))
        self.assertIsNone(self.read("---\nname: -lead\ndescription: d\n---\nb"))
        self.assertIsNone(self.read("---\nname: " + "x" * 257 + "\ndescription: d\n---\nb"))

    def test_opening_fence_must_be_first_line(self):
        self.assertIsNone(self.read("\n---\nname: r\ndescription: d\n---\nb"))


class DiscoverAgentsTest(unittest.TestCase):
    def test_walks_up_to_repository_root_and_closest_wins(self):
        with _PluginModules() as m, tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / ".git").mkdir()
            write_agent(root / ".claude" / "agents", "reviewer", model="haiku")
            write_agent(root / ".claude" / "agents", "top", model="opus")
            sub = root / "pkg" / "inner"
            write_agent(sub / ".claude" / "agents", "reviewer", model="sonnet")
            agents = m.guard.discover_agents(m.guard.agent_search_dirs(str(sub), ""))
            self.assertEqual(agents["reviewer"]["model"], "sonnet")
            self.assertEqual(agents["top"]["model"], "opus")

    def test_does_not_walk_above_repository_root(self):
        with _PluginModules() as m, tempfile.TemporaryDirectory() as d:
            outer = pathlib.Path(d)
            write_agent(outer / ".claude" / "agents", "outside", model="opus")
            repo = outer / "repo"
            (repo / ".git").mkdir(parents=True)
            agents = m.guard.discover_agents(m.guard.agent_search_dirs(str(repo), ""))
            self.assertNotIn("outside", agents)

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
                {"tool_name": "Agent", "tool_input": {"subagent_type": "ghost", "model": "ghost-model"}},
                {"CLAUDE_PROJECT_DIR": str(root), "HOME": str(root / "no-home")})
            self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn("ghost-model", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_builtin_agent_is_allowed_by_hook(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            out = self.m.guard_hook.run(
                {"tool_name": "Agent", "tool_input": {"subagent_type": "Explore"}},
                {"CLAUDE_PROJECT_DIR": str(root), "HOME": str(root / "no-home")})
            self.assertIsNone(out)

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


class PluginPackagingTest(unittest.TestCase):
    """Static shape checks for what `claude plugin validate` rejects (verified against CLI 2.1.325)."""

    def test_hooks_json_has_top_level_hooks_wrapper(self):
        import json
        doc = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("hooks", doc)
        self.assertNotIn("PreToolUse", doc)
        entry = doc["hooks"]["PreToolUse"][0]
        import re
        for tool in ("Agent", "Task"):
            self.assertTrue(re.search(entry["matcher"], tool), tool)
        self.assertFalse(re.search(entry["matcher"], "Read"))
        self.assertIn("CLAUDE_PLUGIN_ROOT", entry["hooks"][0]["command"])

    def test_marketplace_lists_the_plugin_with_matching_name(self):
        import json
        mp_root = ROOT / "adapters" / "claude-code"
        mp = json.loads((mp_root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        entry = mp["plugins"][0]
        self.assertEqual(entry["name"], manifest["name"])
        self.assertTrue((mp_root / entry["source"] / ".claude-plugin" / "plugin.json").is_file())
        self.assertNotIn("..", entry["source"])

    def test_docs_do_not_claim_effort_is_unsupported_per_agent(self):
        for p in (PLUGIN / "README.md", PLUGIN / "skills" / "subagent-orchestration" / "SKILL.md",
                  ROOT / "adapters" / "claude-code" / "README.md"):
            text = p.read_text(encoding="utf-8").lower()
            self.assertNotIn("no per-agent effort", text, p.name)
            self.assertNotIn("has no field for it", text, p.name)

    def test_install_docs_point_at_the_plugin_dir_not_its_parent(self):
        text = (PLUGIN / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("claude-code/plugin\n", text)
        self.assertIn("marketplace add", text)
        self.assertIn("plugin/subagent-routing-kit", text)


if __name__ == "__main__":
    unittest.main()
