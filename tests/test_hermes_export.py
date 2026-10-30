"""Hermes 어댑터의 model_map 내보내기 테스트. Hermes 설치 없이 실행된다(설치본 검사는 validate_installed.py)."""
import copy
import json
import pathlib
import unittest

from adapters.hermes import export_model_map as E

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPECS = json.loads(E.SPECS.read_text(encoding="utf-8"))


class Export(unittest.TestCase):
    def test_committed_proposal_matches_the_specs_byte_for_byte(self):
        self.assertEqual(E.OUT.read_text(encoding="utf-8"), E.render(SPECS))

    def test_one_option_per_spec_in_order_with_only_allowed_keys(self):
        options = E.build_options(SPECS)
        self.assertEqual([o["name"] for o in options], [s["name"] for s in SPECS])
        for o in options:
            self.assertLessEqual(set(o), E.ALLOWED_KEYS)
            self.assertEqual(o["provider"], "openrouter")
            self.assertEqual(o["fallback_providers"], [])

    def test_description_states_effort_speed_and_prohibitions(self):
        s = SPECS[0]
        d = E.describe(s)
        self.assertIn(f"추론={s['reasoning_effort']}", d)
        self.assertIn(f"속도={s['service_tier']}", d)
        self.assertIn("사용 금지:", d)
        self.assertIn("실측 전", d)

    def test_measured_latency_is_reported_as_measured(self):
        s = dict(SPECS[0], latency_measured=True)
        self.assertNotIn("실측 전", E.describe(s))

    def test_default_route_is_declared(self):
        self.assertIn(E.DEFAULT_ROUTE, [s["name"] for s in SPECS])


class Problems(unittest.TestCase):
    def options(self):
        return E.build_options(SPECS)

    def test_clean_proposal_has_no_problems(self):
        self.assertEqual(E.problems(self.options(), E.DEFAULT_ROUTE), [])

    def test_unreadable_extra_key_is_rejected(self):
        o = self.options()
        o[0]["extra_body"] = {"provider": {"sort": "latency"}}
        self.assertTrue(any("extra_body" in e for e in E.problems(o, E.DEFAULT_ROUTE)))

    def test_nonempty_fallback_is_rejected(self):
        o = self.options()
        o[0]["fallback_providers"] = ["openrouter"]
        self.assertTrue(any("폴백" in e for e in E.problems(o, E.DEFAULT_ROUTE)))

    def test_missing_default_is_rejected(self):
        self.assertTrue(any("기본 경로" in e for e in E.problems(self.options(), "Ghost")))

    def test_duplicate_names_are_rejected(self):
        o = self.options()
        o.append(copy.deepcopy(o[0]))
        self.assertTrue(any("중복" in e for e in E.problems(o, E.DEFAULT_ROUTE)))

    def test_option_that_drifts_from_the_spec_is_rejected(self):
        o = self.options()
        o[0]["reasoning_effort"] = "low"
        self.assertTrue(any("명세와 다른" in e for e in E.problems(o, E.DEFAULT_ROUTE)))

    def test_core_hard_rules_apply_to_exported_routes(self):
        # 명세와 옵션을 함께 바꿔도 core 규칙이 잡는다: GLM 은 추론 필수라 none 이 불가능
        specs = copy.deepcopy(SPECS)
        glm = next(s for s in specs if s["model"] == "z-ai/glm-5.3-flash")
        glm["reasoning_effort"] = "none"
        tmp = ROOT / "tests" / "_tmp_specs.json"
        tmp.write_text(json.dumps(specs, ensure_ascii=False), encoding="utf-8")
        try:
            errs = E.problems(E.build_options(specs), E.DEFAULT_ROUTE, specs_path=tmp)
        finally:
            tmp.unlink()
        self.assertTrue(any("effort_cannot_disable" in e for e in errs), errs)

    def test_render_refuses_to_write_an_invalid_proposal(self):
        specs = copy.deepcopy(SPECS)
        specs[0]["service_tier"] = "fast"
        with self.assertRaises(SystemExit):
            E.render(specs)


if __name__ == "__main__":
    unittest.main()
