"""출력 계약 스키마(core/spec/output-contract.schema.json)와 검증기 테스트."""
import json
import pathlib
import re
import unittest

from core.contract import SCHEMA_PATH, load_schema, parse_and_validate, validate

ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY = ROOT / "core" / "policy" / "task-contract.md"


def good(**over):
    doc = {
        "status": "completed",
        "result": "done",
        "evidence": [{"path_or_url": "tests/x.py", "check": "ran"}],
        "artifacts": [],
        "checks": [],
        "unresolved": [],
    }
    doc.update(over)
    return doc


class SchemaFile(unittest.TestCase):
    def test_schema_is_valid_json_with_declared_dialect(self):
        s = load_schema()
        self.assertEqual(s["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(s["type"], "object")
        self.assertIs(s["additionalProperties"], False)

    def test_schema_only_uses_keywords_the_validator_supports(self):
        # 지원하지 않는 키워드가 있으면 validate 가 예외를 던진다.
        self.assertEqual(validate(good()), [])

    def test_policy_example_matches_schema_fields(self):
        text = POLICY.read_text(encoding="utf-8")
        example = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))
        self.assertEqual(set(example), set(load_schema()["properties"]) - {"end", "scope_changes"})
        self.assertIn("output-contract.schema.json", text)

    def test_status_enum_matches_policy(self):
        text = POLICY.read_text(encoding="utf-8")
        for v in load_schema()["properties"]["status"]["enum"]:
            self.assertIn(v, text)

    def test_end_enum_matches_task_contract_end_field(self):
        text = POLICY.read_text(encoding="utf-8")
        for v in load_schema()["properties"]["end"]["enum"]:
            self.assertIn(v, text)


class Validation(unittest.TestCase):
    def test_accepts_minimal_required_only(self):
        self.assertEqual(validate({"status": "completed", "result": "ok", "unresolved": [],
                                   "evidence": [{"path_or_url": "a", "check": "b"}]}), [])

    def test_accepts_optional_fields(self):
        self.assertEqual(validate(good(end="criteria met", scope_changes=["touched b.py"])), [])

    def test_rejects_missing_required(self):
        for key in ("status", "result", "evidence", "unresolved"):
            d = good()
            del d[key]
            self.assertTrue(validate(d), key)

    def test_rejects_bad_status(self):
        self.assertTrue(validate(good(status="done")))

    def test_rejects_unknown_field(self):
        self.assertTrue(validate(good(extra=1)))

    def test_rejects_wrong_types(self):
        self.assertTrue(validate(good(result=5)))
        self.assertTrue(validate(good(artifacts="a.py")))
        self.assertTrue(validate(good(evidence=[{"path_or_url": "a"}])))
        self.assertTrue(validate(good(evidence=[{"path_or_url": "", "check": "b"}])))

    def test_completed_requires_evidence(self):
        self.assertTrue(validate(good(evidence=[])))

    def test_partial_and_blocked_require_unresolved(self):
        for st in ("partial", "blocked"):
            self.assertTrue(validate(good(status=st, evidence=[])), st)
            self.assertEqual(validate(good(status=st, evidence=[], unresolved=["needs X"])), [], st)

    def test_non_object_rejected(self):
        self.assertTrue(validate([]))
        self.assertTrue(validate("completed"))

    def test_bool_is_not_a_string_or_integer(self):
        self.assertTrue(validate(good(result=True)))

    def test_parse_and_validate(self):
        value, errs = parse_and_validate(json.dumps(good()))
        self.assertEqual(errs, [])
        self.assertEqual(value["status"], "completed")
        value, errs = parse_and_validate("not json")
        self.assertIsNone(value)
        self.assertEqual(len(errs), 1)

    def test_unsupported_keyword_fails_loudly(self):
        with self.assertRaises(ValueError):
            validate({"a": 1}, {"type": "object", "pattern": "x"})


class DefaultSchemaCache(unittest.TestCase):
    def test_default_schema_is_read_once(self):
        from unittest import mock

        from core import contract

        contract._default_schema.cache_clear()
        with mock.patch.object(contract, "load_schema", wraps=contract.load_schema) as m:
            for _ in range(5):
                self.assertEqual(validate(good()), [])
        self.assertEqual(m.call_count, 1)
        contract._default_schema.cache_clear()


class SchemaLocation(unittest.TestCase):
    def test_default_path(self):
        self.assertTrue(SCHEMA_PATH.is_file())


if __name__ == "__main__":
    unittest.main()
