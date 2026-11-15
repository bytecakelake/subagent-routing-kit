"""Codex 플러그인 패키지(매니페스트·훅 설정·마켓플레이스·동기화·스냅샷)를 검사한다.

CODEX_BIN 환경변수에 실제 codex 실행 파일을 주면 별도 HOME/CODEX_HOME 에서 로컬 마켓플레이스 add 와
plugin add 를 실제로 수행한다(선택 검사, 사용자 인증·비밀을 쓰지 않는다). 없으면 그 검사만 건너뛴다.
"""
import ast
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "codex"
MARKET = ADAPTER / "marketplace"
PLUGIN = MARKET / "plugins" / "subagent-routing-kit"

sys.path.insert(0, str(ROOT))
from core.eligibility import ModelCaps  # noqa: E402


def read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


class ManifestTest(unittest.TestCase):
    def test_manifest_identity_and_components(self):
        m = read_json(PLUGIN / ".codex-plugin" / "plugin.json")
        self.assertEqual(m["name"], "subagent-routing-kit")
        self.assertRegex(m["version"], r"^\d+\.\d+\.\d+$")
        self.assertTrue(m["description"])
        self.assertEqual(m["skills"], "./skills/")
        self.assertTrue((PLUGIN / "skills" / "subagent-orchestration" / "SKILL.md").is_file())
        # hooks 를 매니페스트에 적으면 hooks/hooks.json 기본 탐색을 대체한다. 어느 쪽이든 가리키는 파일은 있어야 한다.
        hooks = m.get("hooks")
        if hooks is not None:
            for ref in ([hooks] if isinstance(hooks, str) else hooks):
                self.assertTrue(ref.startswith("./"), ref)
                self.assertTrue((PLUGIN / ref).is_file(), ref)

    def test_skill_frontmatter(self):
        text = (PLUGIN / "skills" / "subagent-orchestration" / "SKILL.md").read_text(encoding="utf-8")
        front = re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1)
        self.assertRegex(front, r"(?m)^name: subagent-orchestration$")
        self.assertRegex(front, r"(?m)^description: .+")
        # 강제한다고 주장하지 않는다
        self.assertNotRegex(text.lower(), r"guarantee|always enforced|enforces every")


class HooksConfigTest(unittest.TestCase):
    def setUp(self):
        self.cfg = read_json(PLUGIN / "hooks" / "hooks.json")

    def test_top_level_hooks_wrapper(self):
        # 이벤트 이름이 최상위에 바로 오면 Codex 가 훅으로 읽지 않는다. 반드시 "hooks" 래퍼 안에 둔다.
        self.assertIn("hooks", self.cfg)
        self.assertNotIn("PreToolUse", self.cfg)
        self.assertEqual(set(self.cfg["hooks"]), {"PreToolUse"})

    def test_matcher_covers_v1_v2_and_alias_but_not_other_tools(self):
        groups = self.cfg["hooks"]["PreToolUse"]
        self.assertEqual(len(groups), 1)
        pattern = re.compile(groups[0]["matcher"])
        for name in ("spawn_agent", "Agent", "collaborationspawn_agent"):
            self.assertTrue(pattern.search(name), name)
        for name in ("Bash", "apply_patch", "send_message", "wait_agent"):
            self.assertFalse(pattern.search(name), name)

    def test_command_uses_plugin_root_and_points_at_real_script(self):
        (hook,) = self.cfg["hooks"]["PreToolUse"][0]["hooks"]
        self.assertEqual(hook["type"], "command")
        self.assertIn("${PLUGIN_ROOT}/scripts/guard_hook.py", hook["command"])
        self.assertTrue((PLUGIN / "scripts" / "guard_hook.py").is_file())
        self.assertIsInstance(hook["timeout"], int)
        self.assertNotIn("async", hook)  # 비동기 훅은 차단할 수 없다


class MarketplaceTest(unittest.TestCase):
    def test_marketplace_entry_resolves_to_plugin(self):
        mk = read_json(MARKET / ".agents" / "plugins" / "marketplace.json")
        self.assertTrue(mk["name"])
        (entry,) = mk["plugins"]
        self.assertEqual(entry["name"], "subagent-routing-kit")
        self.assertEqual(entry["source"], {"source": "local", "path": "./plugins/subagent-routing-kit"})
        self.assertTrue((MARKET / entry["source"]["path"] / ".codex-plugin" / "plugin.json").is_file())
        self.assertIn(entry["policy"]["installation"], {"AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"})
        self.assertIn("authentication", entry["policy"])
        self.assertTrue(entry["category"])


class RuntimeBoundaryTest(unittest.TestCase):
    STDLIB = set(sys.stdlib_module_names)

    def test_plugin_scripts_import_only_stdlib_or_each_other(self):
        local = {p.stem for p in (PLUGIN / "scripts").glob("*.py")}
        for path in (PLUGIN / "scripts").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                for n in names:
                    self.assertIn(n, self.STDLIB | local, f"{path.name}: {n}")


class SyncTest(unittest.TestCase):
    def test_copies_match_sources(self):
        try:
            from adapters.codex import sync_plugin
        except ImportError as exc:  # typer 미설치
            self.skipTest(str(exc))
        drift = [dst.relative_to(ROOT).as_posix() for src, dst in sync_plugin.MAPPING.items()
                 if not dst.exists() or dst.read_bytes() != src.read_bytes()]
        self.assertEqual(drift, [])

    def test_core_rules_copy_is_byte_identical(self):
        self.assertEqual((PLUGIN / "scripts" / "eligibility_rules.py").read_bytes(),
                         (ROOT / "core" / "eligibility" / "rules.py").read_bytes())


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.doc = read_json(ADAPTER / "model-capabilities.json")

    def test_plugin_copy_equals_source(self):
        self.assertEqual((PLUGIN / "scripts" / "capabilities.json").read_bytes(),
                         (ADAPTER / "model-capabilities.json").read_bytes())

    def test_provenance_is_recorded(self):
        src = self.doc["source"]
        self.assertEqual(src["codex_version"], "0.169.0")
        self.assertIn("debug models --bundled", src["command"])
        self.assertRegex(self.doc["collected_at"], r"^\d{4}-\d{2}-\d{2}$")

    def test_every_entry_loads_and_has_no_invented_values(self):
        self.assertGreater(len(self.doc["models"]), 0)
        for slug, entry in self.doc["models"].items():
            caps = ModelCaps.from_dict(slug, entry)
            self.assertTrue(caps.supported_efforts, slug)
            self.assertNotIn("none", caps.supported_efforts, slug)
            self.assertIsNone(caps.long_context_surcharge_tokens, slug)  # 카탈로그에 없다 -> 모름
            self.assertFalse(caps.free, slug)

    def test_hidden_models_are_excluded_and_listed(self):
        self.assertTrue(set(self.doc["excluded_hidden"]).isdisjoint(self.doc["models"]))


class CollectCapabilitiesTest(unittest.TestCase):
    CATALOG = {"models": [
        {"slug": "m-a", "visibility": "list", "context_window": 1000, "max_context_window": 5000,
         "input_modalities": ["text", "image"], "multi_agent_version": "v2",
         "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}]},
        {"slug": "m-hidden", "visibility": "hide", "context_window": 1, "input_modalities": ["text"],
         "supported_reasoning_levels": [{"effort": "low"}]},
    ]}

    def setUp(self):
        try:
            from adapters.codex import collect_capabilities
        except ImportError as exc:
            self.skipTest(str(exc))
        self.build = collect_capabilities.build_snapshot

    def test_build_snapshot(self):
        doc = self.build(self.CATALOG, codex_version="9.9.9", collected_at="2026-01-02")
        self.assertEqual(list(doc["models"]), ["m-a"])
        self.assertEqual(doc["excluded_hidden"], ["m-hidden"])
        e = doc["models"]["m-a"]
        self.assertEqual(e["context_tokens"], 1000)
        self.assertEqual(e["max_context_window"], 5000)
        self.assertEqual(e["supported_efforts"], ["low", "high"])
        self.assertEqual(e["input_modalities"], ["image", "text"])
        self.assertTrue(e["supports_reasoning"] and e["reasoning_mandatory"])
        self.assertIsNone(e["long_context_surcharge_tokens"])
        self.assertEqual(doc["source"]["codex_version"], "9.9.9")

    def test_model_without_reasoning_levels_is_rejected_loudly(self):
        bad = {"models": [{"slug": "x", "visibility": "list", "context_window": 1,
                           "input_modalities": ["text"], "supported_reasoning_levels": []}]}
        with self.assertRaises(ValueError):
            self.build(bad, codex_version="1", collected_at="2026-01-02")


@unittest.skipUnless(os.environ.get("CODEX_BIN"), "CODEX_BIN 이 없어 실제 Codex CLI 설치 검사를 건너뜀")
class RealCodexInstallTest(unittest.TestCase):
    """실제 CLI 로 로컬 마켓플레이스 add + plugin add 를 격리된 HOME/CODEX_HOME 에서 수행한다."""

    def test_marketplace_add_and_plugin_add(self):
        codex = os.environ["CODEX_BIN"]
        with tempfile.TemporaryDirectory() as tmp:
            home, chome = pathlib.Path(tmp, "home"), pathlib.Path(tmp, "codex")
            home.mkdir()
            chome.mkdir()
            env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "CODEX_HOME": str(chome)}

            def run(*args):
                return subprocess.run([codex, *args], env=env, capture_output=True, text=True, timeout=120)

            r = run("plugin", "marketplace", "add", str(MARKET))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = run("plugin", "add", "subagent-routing-kit@subagent-routing-kit", "--json")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            installed = list(chome.glob("plugins/cache/*/subagent-routing-kit/*/"))
            self.assertEqual(len(installed), 1, installed)
            root = installed[0]
            for rel in (".codex-plugin/plugin.json", "hooks/hooks.json", "scripts/guard_hook.py",
                        "scripts/guard.py", "scripts/eligibility_rules.py", "scripts/capabilities.json",
                        "skills/subagent-orchestration/SKILL.md"):
                self.assertTrue((root / rel).is_file(), rel)

            # 런타임이 훅을 찾는지: app-server 의 hooks/list. 설치만으로는 신뢰되지 않아야 한다.
            hook = self._discovered_hook(codex, env)
            self.assertEqual(hook["source"], "plugin")
            self.assertEqual(hook["eventName"], "preToolUse")
            self.assertEqual(hook["matcher"], "spawn_agent|Agent")
            self.assertEqual(hook["trustStatus"], "untrusted")
            self.assertTrue(hook["enabled"] and not hook["isManaged"])
            self.assertIn(str(root), hook["command"])  # ${PLUGIN_ROOT} 가 설치 경로로 풀렸다

            # 런타임이 풀어 준 명령을 그대로(셸로) 실행해 설치본이 동작하는지 본다. 신뢰 승인·모델 호출은 하지 않는다.
            stdin = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "spawn_agent", "cwd": tmp,
                                "tool_input": {"message": "m", "model": "nope-9", "reasoning_effort": "low"}})
            # shell=True 는 Codex 가 쓰는 방식(문자열 명령)을 재현하려는 것이며, 명령은 이 저장소의 hooks.json 에서 온다.
            r = subprocess.run(hook["command"], shell=True, input=stdin, capture_output=True, text=True,
                               env={**env, "PLUGIN_ROOT": str(root)}, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    @staticmethod
    def _discovered_hook(codex, env):
        import select
        p = subprocess.Popen([codex, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, env=env)
        try:
            def send(obj):
                p.stdin.write(json.dumps(obj) + "\n")
                p.stdin.flush()

            def reply(want_id):
                while select.select([p.stdout], [], [], 30)[0]:
                    msg = json.loads(p.stdout.readline() or "{}")
                    if msg.get("id") == want_id:
                        return msg
                raise AssertionError("app-server did not answer")

            send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "t", "version": "0"}}})
            reply(1)
            send({"method": "initialized"})
            send({"id": 2, "method": "hooks/list", "params": {"cwds": [str(ROOT)]}})
            hooks = reply(2)["result"]["data"][0]["hooks"]
            mine = [h for h in hooks if h.get("pluginId") == "subagent-routing-kit@subagent-routing-kit"]
            assert len(mine) == 1, hooks
            return mine[0]
        finally:
            p.kill()
            p.wait()


if __name__ == "__main__":
    unittest.main()
