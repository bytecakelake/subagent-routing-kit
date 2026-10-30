"""실제 변형 명세(core/spec)와 수집된 모델 능력(model-capabilities.json)에 대한 판정 테스트.

이 파일의 일부 단언은 수집 시점의 공개 메타데이터에 의존한다. 모델 능력을 다시 수집한 뒤 실패하면
데이터가 바뀐 것이므로 명세를 검토하고 기대값을 갱신한다.
"""
import json
import pathlib
import unittest

from core.catalog.build_capabilities import extract_caps
from core.eligibility import Route, Task, evaluate, load_capabilities, routes_from_specs
from core.eligibility import rules as R

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPECS = ROOT / "core" / "spec" / "variant-specs.json"
CAPS_FILE = ROOT / "core" / "spec" / "model-capabilities.json"

CAPS = load_capabilities(CAPS_FILE)
ROUTES = routes_from_specs(SPECS)
NAMES = [r.name for r in ROUTES]


def decide(task, routes=ROUTES, registered=NAMES):
    return evaluate(task, routes, CAPS, registered=registered)


class SpecIntegrity(unittest.TestCase):
    def test_every_spec_model_has_capabilities(self):
        self.assertEqual({r.model for r in ROUTES} - set(CAPS), set())

    def test_route_names_are_unique(self):
        self.assertEqual(len(NAMES), len(set(NAMES)))

    def test_all_17_variants_pass_the_task_independent_rules(self):
        d = decide(Task("baseline"))
        self.assertEqual(len(ROUTES), 17)
        self.assertEqual(d.rejected, {}, d.rejected)
        self.assertEqual(d.status, R.ELIGIBLE)

    def test_capabilities_file_records_provenance(self):
        doc = json.loads(CAPS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema"], 1)
        self.assertRegex(doc["collected_at"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue(doc["source"])


class RegressionAgainstEarlierValidation(unittest.TestCase):
    """초기 오프라인 검증(옛 variant-validation.json, git 이력)에서 거부되어야 한다고 확인한 사례를 같은 판정기로 다시 확인한다."""

    def violations(self, model, effort, tier="normal"):
        r = Route("probe", model, effort, tier)
        return R.route_violations(r, CAPS, {"probe": r})

    def test_glm_unlisted_effort_is_rejected(self):
        self.assertEqual(self.violations("z-ai/glm-5.3-flash", "medium"), [R.EFFORT_UNADVERTISED])

    def test_glm_cannot_be_disabled(self):
        self.assertEqual(self.violations("z-ai/glm-5.3-flash", "none"), [R.EFFORT_CANNOT_DISABLE])

    def test_deepseek_pro_medium_is_rejected(self):
        self.assertEqual(self.violations("deepseek/deepseek-v4-pro", "medium"), [R.EFFORT_UNADVERTISED])

    def test_models_with_undisclosed_efforts_reject_invented_efforts(self):
        for model in ("qwen/qwen3.8-flash", "xiaomi/mimo-v2.6-flash", "nvidia/nemotron-3.5-super-vl:free"):
            self.assertEqual(self.violations(model, "high"), [R.EFFORT_UNADVERTISED], model)

    def test_fast_and_ultrafast_are_rejected(self):
        for tier in ("fast", "ultrafast"):
            self.assertEqual(self.violations("openai/gpt-6.1-terra", "low", tier), [R.SERVICE_TIER_UNVERIFIED], tier)

    def test_implicit_effort_is_rejected(self):
        self.assertEqual(self.violations("openai/gpt-6.1-terra", None), [R.EFFORT_IMPLICIT])


class TaskScenarios(unittest.TestCase):
    def test_long_input_excludes_exactly_the_haiku_variants(self):
        d = decide(Task("long", input_tokens=150_000))
        self.assertEqual(set(d.rejected), {"M-Haiku-Quick", "M-Haiku-Balanced"})
        self.assertTrue(all(v == (R.LONG_CONTEXT_SURCHARGE,) for v in d.rejected.values()))

    def test_input_just_below_haiku_threshold_keeps_haiku(self):
        d = decide(Task("short", input_tokens=99_999))
        self.assertIn("M-Haiku-Balanced", d.eligible)

    def test_unknown_input_length_warns_for_surcharge_models_only(self):
        d = decide(Task("unknown", input_tokens=None))
        self.assertEqual(set(d.warnings), {"M-Haiku-Quick", "M-Haiku-Balanced", "F-Sol-Standard", "F-Sol-Deep",
                                           "M-Terra-Quick", "M-Terra-Balanced", "M-Terra-Deep"})

    def test_image_task_excludes_text_only_models(self):
        d = decide(Task("img", needs_modalities=frozenset({"text", "image"})))
        self.assertEqual(set(d.rejected), {"M-DeepSeekPro-Plain", "M-DeepSeekPro-Reason"})

    def test_direct_audio_is_limited_to_audio_capable_models(self):
        d = decide(Task("audio", needs_modalities=frozenset({"text", "audio"})))
        self.assertEqual(set(d.eligible), {"MM-MiMo-Inspect", "MM-Gemini-Inspect", "MM-Gemini-Reason"})

    def test_registered_subset_limits_candidates(self):
        d = decide(Task("t"), registered=["M-Terra-Quick", "L-GLM-Extract"])
        self.assertEqual(set(d.eligible), {"M-Terra-Quick", "L-GLM-Extract"})
        self.assertTrue(all(v == (R.ROUTE_NOT_REGISTERED,) for v in d.rejected.values()))

    def test_nothing_registered_goes_to_parent(self):
        d = decide(Task("t"), registered=[])
        self.assertEqual((d.status, d.eligible), (R.NEEDS_PARENT, ()))

    def test_free_route_has_no_paid_fallback_in_the_specs(self):
        free = [r for r in ROUTES if CAPS[r.model].free]
        self.assertEqual([r.name for r in free], ["Free-Nemotron-Visual"])
        self.assertEqual(free[0].fallback_routes, ())


class Collector(unittest.TestCase):
    def test_extract_caps_from_api_shape(self):
        api = {
            "context_length": 262144,
            "architecture": {"input_modalities": ["text", "image"]},
            "supported_parameters": ["tools", "reasoning"],
            "reasoning": {"mandatory": True, "supported_efforts": ["high", "low"]},
            "pricing": {"prompt": "0.000001", "completion": "0.000002",
                        "overrides": [{"min_prompt_tokens": 200000}, {"min_prompt_tokens": 100000}]},
        }
        self.assertEqual(extract_caps(api), {
            "context_tokens": 262144, "input_modalities": ["image", "text"], "supports_tools": True,
            "supports_reasoning": True, "reasoning_mandatory": True, "supported_efforts": ["high", "low"],
            "long_context_surcharge_tokens": 100000, "free": False})

    def test_missing_effort_list_is_none_not_empty(self):
        caps = extract_caps({"supported_parameters": ["reasoning"], "reasoning": {"mandatory": False},
                             "pricing": {"prompt": "0", "completion": "0"}})
        self.assertIsNone(caps["supported_efforts"])
        self.assertTrue(caps["free"])

    def test_model_without_reasoning_field(self):
        caps = extract_caps({"supported_parameters": [], "pricing": {"prompt": "1", "completion": "1"}})
        self.assertFalse(caps["supports_reasoning"])
        self.assertFalse(caps["reasoning_mandatory"])


if __name__ == "__main__":
    unittest.main()
