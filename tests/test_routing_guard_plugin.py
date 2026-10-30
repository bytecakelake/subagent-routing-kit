"""routing-guard 플러그인의 Hermes 연결부(register → pre_tool_call 훅)를 검사한다.

Hermes 를 띄우지 않고, 훅이 받는 인자와 설정 로더만 흉내 내어 배선이 맞는지 확인한다.
"""
import importlib.util
import json
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "adapters" / "hermes" / "plugin" / "routing-guard"
PROPOSAL = json.loads((ROOT / "adapters" / "hermes" / "model-map-proposal.json").read_text(encoding="utf-8"))


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "routing_guard_plugin", PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)])
    module = importlib.util.module_from_spec(spec)
    sys.modules["routing_guard_plugin"] = module
    spec.loader.exec_module(module)
    return module


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.hooks = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, callback):
        self.hooks[name] = callback


def config_with(options=None, default=None, backend="model_map"):
    return {"delegation": {"backend": backend, "backends": {"model_map": {
        "options": options if options is not None else PROPOSAL["options"],
        "default": default if default is not None else PROPOSAL["default"]}}}}


class PluginWiringTest(unittest.TestCase):
    def setUp(self):
        self.plugin = load_plugin()
        self.ctx = FakeCtx()
        self.plugin.register(self.ctx)
        self.hook = self.ctx.hooks["pre_tool_call"]
        self.config = config_with()
        stub = types.ModuleType("hermes_cli.config")
        stub.load_config_readonly = lambda: self.config
        self._saved = {k: sys.modules.get(k) for k in ("hermes_cli", "hermes_cli.config")}
        sys.modules["hermes_cli"] = types.ModuleType("hermes_cli")
        sys.modules["hermes_cli.config"] = stub

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    def test_hook_registered(self):
        self.assertIn("pre_tool_call", self.ctx.hooks)

    def test_valid_route_passes(self):
        self.assertIsNone(self.hook("delegate_task", {"tasks": [{"goal": "x", "option": "F-Sol-Deep"}]}))

    def test_other_tool_is_ignored(self):
        self.assertIsNone(self.hook("read_file", {"path": "a"}))

    def test_violating_route_returns_block_directive(self):
        for option in self.config["delegation"]["backends"]["model_map"]["options"]:
            if option["name"] == "L-GLM-Extract":
                option["reasoning_effort"] = "none"
        result = self.hook("delegate_task", {"tasks": [{"goal": "x", "option": "L-GLM-Extract"}]})
        self.assertEqual("block", result["action"])
        self.assertIn("effort_cannot_disable", result["message"])

    def test_broken_guard_fails_open(self):
        self.config = None  # load_config_readonly 가 None 을 돌려주는 상황
        sys.modules["hermes_cli.config"].load_config_readonly = lambda: None
        self.assertIsNone(self.hook("delegate_task", {"tasks": [{"goal": "x", "option": "F-Sol-Deep"}]}))

    def test_non_strict_setting_is_read(self):
        ctx = FakeCtx({"strict_unknown_model": False})
        self.plugin.register(ctx)
        self.config = config_with(options=[dict(PROPOSAL["options"][0], model="unknown/model-x")])
        sys.modules["hermes_cli.config"].load_config_readonly = lambda: self.config
        hook = ctx.hooks["pre_tool_call"]
        self.assertIsNone(hook("delegate_task", {"tasks": [{"goal": "x", "option": PROPOSAL["options"][0]["name"]}]}))


if __name__ == "__main__":
    unittest.main()
