"""core.jsonio(orjson) 와 표준 json 의 동등성, 알려진 차이에 대한 안전망."""
import json
import pathlib
import unittest

from core import jsonio

ROOT = pathlib.Path(__file__).resolve().parents[1]
JSON_FILES = sorted((ROOT / "core" / "spec").glob("*.json")) + [ROOT / "adapters" / "hermes" / "model-map-proposal.json"]


def walk(v):
    yield v
    if isinstance(v, dict):
        for x in v.values():
            yield from walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from walk(x)


class Equivalence(unittest.TestCase):
    def test_loads_matches_stdlib_for_repo_json(self):
        for p in JSON_FILES:
            self.assertEqual(jsonio.load_path(p), json.loads(p.read_text(encoding="utf-8")), p.name)

    def test_indented_dump_is_byte_identical_to_stdlib(self):
        for p in JSON_FILES:
            obj = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(jsonio.dumps(obj, indent=True), json.dumps(obj, indent=2, ensure_ascii=False), p.name)

    def test_sorted_dump_matches_stdlib(self):
        obj = {"b": 1, "a": {"z": [1, 2], "y": "한글"}, "한": 0, "A": 2}
        self.assertEqual(jsonio.dumps(obj, indent=True, sort_keys=True),
                         json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True))

    def test_generated_capabilities_format_is_stable(self):
        # build_capabilities 가 쓰는 형식(정렬, 2칸 들여쓰기, 끝 개행)으로 다시 써도 저장된 파일과 같아야 한다.
        p = ROOT / "core" / "spec" / "model-capabilities.json"
        doc = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(jsonio.dumps(doc, indent=True, sort_keys=True) + "\n", p.read_text(encoding="utf-8"))

    def test_compact_dump_has_no_spaces(self):
        self.assertEqual(jsonio.dumps({"a": [1, 2]}), '{"a":[1,2]}')


class KnownDifferences(unittest.TestCase):
    """orjson 이 표준 json 과 다르게 동작하는 점. 바뀌면(업그레이드 등) 알아챌 수 있게 고정한다."""

    def test_huge_integer_is_silently_a_float_on_read(self):
        v = jsonio.loads("123456789012345678901234567890")
        self.assertIsInstance(v, float)

    def test_unrepresentable_values_fail_loudly_on_write(self):
        for bad in (2**70, {1: "a"}, "\ud800"):
            with self.assertRaises(TypeError):
                jsonio.dumps(bad)

    def test_nan_literal_is_rejected_on_read(self):
        with self.assertRaises(jsonio.JSONDecodeError):
            jsonio.loads("[NaN]")

    def test_decode_error_is_a_stdlib_decode_error(self):
        self.assertTrue(issubclass(jsonio.JSONDecodeError, json.JSONDecodeError))


class RepoDataIsSafeForOrjson(unittest.TestCase):
    """위 차이 중 읽기 쪽 위험(큰 정수의 무음 변환)이 저장소 데이터에 없음을 보장한다."""

    def test_no_integer_beyond_64_bit_in_repo_json(self):
        for p in JSON_FILES:
            for v in walk(json.loads(p.read_text(encoding="utf-8"))):
                if isinstance(v, int) and not isinstance(v, bool):
                    self.assertLess(abs(v), 2**63, f"{p.name}: {v}")

    def test_no_float_nan_or_infinity_in_repo_json(self):
        for p in JSON_FILES:
            for v in walk(json.loads(p.read_text(encoding="utf-8"))):
                if isinstance(v, float):
                    self.assertEqual(v, v, p.name)
                    self.assertNotIn(v, (float("inf"), float("-inf")), p.name)


if __name__ == "__main__":
    unittest.main()
