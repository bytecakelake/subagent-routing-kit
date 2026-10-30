"""routing-guard 판정 로직 검사. Hermes 를 띄우지 않고 순수 함수만 호출한다."""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "adapters" / "hermes" / "plugin" / "routing-guard"
sys.path.insert(0, str(PLUGIN))

import guard  # noqa: E402
from guard import rules  # noqa: E402

PROPOSAL = json.loads((ROOT / "adapters" / "hermes" / "model-map-proposal.json").read_text(encoding="utf-8"))
CAPS = rules.load_capabilities(ROOT / "core" / "spec" / "model-capabilities.json")
DEFAULT = PROPOSAL["default"]


def config(options=None, default=DEFAULT, backend="model_map"):
    return {"delegation": {"backend": backend, "backends": {"model_map": {
        "options": options if options is not None else PROPOSAL["options"], "default": default}}}}


def variant(name, **changes):
    """제안 사본에서 한 경로만 바꾼 설정."""
    options = [dict(o) for o in PROPOSAL["options"]]
    for o in options:
        if o["name"] == name:
            o.update(changes)
            if changes.get("reasoning_effort") is None:
                o.pop("reasoning_effort", None)
    return config(options)


class HappyPathTest(unittest.TestCase):
    def test_every_proposed_route_passes(self):
        for option in PROPOSAL["options"]:
            with self.subTest(route=option["name"]):
                args = {"tasks": [{"goal": "do the thing", "option": option["name"]}]}
                self.assertIsNone(guard.guard_call(args, config(), CAPS))

    def test_default_route_used_when_option_omitted(self):
        args = {"tasks": [{"goal": "do the thing"}]}
        self.assertIsNone(guard.guard_call(args, config(), CAPS))

    def test_legacy_single_goal_is_checked_too(self):
        args = {"goal": "do the thing", "option": "F-Sol-Deep"}
        self.assertIsNone(guard.guard_call(args, config(), CAPS))

    def test_image_task_passes_on_vision_route(self):
        args = {"images": ["chart.png"], "tasks": [{"goal": "read the chart", "option": "MM-Gemini-Inspect"}]}
        self.assertIsNone(guard.guard_call(args, config(), CAPS))


class BlockTest(unittest.TestCase):
    def test_unknown_option_is_blocked(self):
        msg = guard.guard_call({"tasks": [{"goal": "x", "option": "F-없는경로"}]}, config(), CAPS)
        self.assertIn("등록된 경로가 아닙니다", msg)

    def test_implicit_effort_is_blocked(self):
        cfg = variant("M-Terra-Deep", reasoning_effort=None)
        msg = guard.guard_call({"tasks": [{"goal": "x", "option": "M-Terra-Deep"}]}, cfg, CAPS)
        self.assertIn(rules.EFFORT_IMPLICIT, msg)

    def test_unadvertised_effort_is_blocked(self):
        cfg = variant("L-GLM-Extract", reasoning_effort="ultra")
        msg = guard.guard_call({"tasks": [{"goal": "x", "option": "L-GLM-Extract"}]}, cfg, CAPS)
        self.assertIn(rules.EFFORT_UNADVERTISED, msg)

    def test_disabling_mandatory_reasoning_is_blocked(self):
        cfg = variant("L-GLM-Extract", reasoning_effort="none")
        msg = guard.guard_call({"tasks": [{"goal": "x", "option": "L-GLM-Extract"}]}, cfg, CAPS)
        self.assertIn(rules.EFFORT_CANNOT_DISABLE, msg)

    def test_unknown_model_is_blocked_and_message_points_at_sync(self):
        cfg = variant("M-Haiku-Quick", model="unknown/model-x")
        msg = guard.guard_call({"tasks": [{"goal": "x", "option": "M-Haiku-Quick"}]}, cfg, CAPS)
        self.assertIn(rules.UNKNOWN_MODEL, msg)
        self.assertIn("sync_plugin.py", msg)

    def test_unknown_model_passes_when_not_strict(self):
        cfg = variant("M-Haiku-Quick", model="unknown/model-x")
        self.assertIsNone(guard.guard_call({"tasks": [{"goal": "x", "option": "M-Haiku-Quick"}]},
                                           cfg, CAPS, strict=False))

    def test_image_task_on_text_only_route_is_blocked(self):
        text_only = [o for o in PROPOSAL["options"] if o["name"] == "M-DeepSeekPro-Plain"]
        self.assertNotIn("image", CAPS[text_only[0]["model"]].input_modalities)
        args = {"images": ["chart.png"], "tasks": [{"goal": "read the chart", "option": "M-DeepSeekPro-Plain"}]}
        msg = guard.guard_call(args, config(), CAPS)
        self.assertIn(f"{rules.MODALITY_UNSUPPORTED}:image", msg)

    def test_free_route_with_fallback_is_blocked(self):
        cfg = variant("Free-Nemotron-Visual", fallback_providers=[{"provider": "openrouter", "model": "x"}])
        msg = guard.guard_call({"tasks": [{"goal": "x", "option": "Free-Nemotron-Visual"}]}, cfg, CAPS)
        self.assertIn(rules.FREE_TO_PAID_FALLBACK, msg)

    def test_block_message_lists_alternatives(self):
        cfg = variant("L-GLM-Extract", reasoning_effort="none")
        msg = guard.guard_call({"tasks": [{"goal": "x", "option": "L-GLM-Extract"}]}, cfg, CAPS)
        self.assertIn("대안:", msg)
        self.assertIn("M-Haiku-Balanced", msg)


class ScopeTest(unittest.TestCase):
    def test_control_actions_are_ignored(self):
        for action in ("list", "steer", "stop"):
            with self.subTest(action=action):
                self.assertIsNone(guard.guard_call({"action": action}, config(), CAPS))

    def test_other_backend_is_ignored(self):
        cfg = config(backend="default")
        self.assertIsNone(guard.guard_call({"tasks": [{"goal": "x", "option": "nope"}]}, cfg, CAPS))

    def test_empty_config_does_not_block(self):
        self.assertIsNone(guard.guard_call({"tasks": [{"goal": "x"}]}, {}, CAPS))


class SyncedCopyTest(unittest.TestCase):
    def test_plugin_copies_match_core(self):
        pairs = {
            PLUGIN / "eligibility_rules.py": ROOT / "core" / "eligibility" / "rules.py",
            PLUGIN / "capabilities.json": ROOT / "core" / "spec" / "model-capabilities.json",
        }
        for copy_path, source in pairs.items():
            with self.subTest(file=copy_path.name):
                self.assertEqual(source.read_bytes(), copy_path.read_bytes(),
                                 f"{copy_path.name} 이 core 와 다릅니다. sync_plugin.py 를 실행하십시오.")


if __name__ == "__main__":
    unittest.main()
