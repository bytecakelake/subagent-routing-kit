"""apply_model_map 의 오프라인 검증과 YAML 블록 생성 검사. 추론·설정 변경은 하지 않는다."""
import json
import pathlib
import unittest

from adapters.hermes import apply_model_map as am


class ProposalTest(unittest.TestCase):
    def setUp(self):
        self.data = am.load()
        self.options = self.data["options"]
        self.default = self.data["default"]

    def test_proposal_passes_all_checks(self):
        self.assertEqual([], am.plugin_problems(self.options, self.default))
        self.assertEqual([], am.problems(self.options, self.default))
        am.check(self.options, self.default)  # 예외가 없어야 한다

    def test_name_rule_rejects_spaces_and_empty(self):
        for bad in ("F Sol", "", "-lead", "x" * 65, "한글경로"):
            with self.subTest(bad=bad):
                self.assertTrue(am.plugin_problems([dict(self.options[0], name=bad)], bad))

    def test_default_must_exist(self):
        self.assertTrue(am.plugin_problems(self.options, "없는-경로"))

    def test_unknown_key_and_effort_are_rejected(self):
        bad_key = [dict(self.options[0], extra_body={"provider": {"sort": "latency"}})]
        self.assertTrue(am.plugin_problems(bad_key, bad_key[0]["name"]))
        bad_effort = [dict(self.options[0], reasoning_effort="turbo")]
        self.assertTrue(am.plugin_problems(bad_effort, bad_effort[0]["name"]))

    def test_fallback_must_be_a_list(self):
        bad = [dict(self.options[0], fallback_providers="openrouter")]
        self.assertTrue(am.plugin_problems(bad, bad[0]["name"]))


class YamlBlockTest(unittest.TestCase):
    def setUp(self):
        data = am.load()
        self.options, self.default = data["options"], data["default"]
        self.block = am.yaml_block(self.options, self.default)

    def test_block_mentions_every_route_once(self):
        for option in self.options:
            self.assertEqual(1, self.block.count(f"- name: {option['name']}\n"))
        self.assertIn(f"default: {self.default}\n", self.block)
        self.assertIn("backend: model_map\n", self.block)

    def test_descriptions_are_quoted_so_colons_survive(self):
        first = self.options[0]
        self.assertIn(f"description: {json.dumps(first['description'], ensure_ascii=False)}", self.block)

    def test_inline_values_are_valid_json_and_equal_the_option_values(self):
        # 공백 없는 JSON 도 YAML 흐름 표기로 유효하다. 줄마다 값을 JSON 으로 읽어 원본과 비교한다.
        rows = {}
        for line in self.block.splitlines():
            key, sep, value = line.strip().partition(": ")
            if sep and key in ("description", "provider", "model", "reasoning_effort", "service_tier", "fallback_providers"):
                rows.setdefault(key, []).append(value)
        for key, values in rows.items():
            want = [o[key] for o in self.options if o.get(key) or (key == "fallback_providers" and o.get(key))]
            got = [json.loads(v) for v in values if v != "[]"]
            self.assertEqual(got, [w for w in want if w], key)

    def test_block_is_ascii_yaml_safe(self):
        # 값에 탭이 섞이면 YAML 이 깨진다. 명세 값 자체를 검사한다.
        for option in self.options:
            for key, value in option.items():
                if isinstance(value, str):
                    self.assertNotIn("\t", value, f"{option['name']}.{key}")
                    self.assertNotIn("\n", value, f"{option['name']}.{key}")

    def test_proposal_is_generated_from_specs(self):
        # 손으로 고친 제안 파일이 명세와 어긋나면 여기서 잡힌다.
        specs = pathlib.Path(am.ROOT) / "core" / "spec" / "variant-specs.json"
        names = [s["name"] for s in json.loads(specs.read_text(encoding="utf-8"))]
        self.assertEqual(names, [o["name"] for o in self.options])


if __name__ == "__main__":
    unittest.main()
