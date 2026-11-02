"""출력 계약: 원본 JSON Schema(core/spec/output-contract.schema.json)와 pydantic 검증기 테스트."""
import json
import pathlib
import re
import unittest
from unittest import mock

from core import contract
from core.contract import END_VALUES, SCHEMA_PATH, Evidence, Report, load_schema, validate

try:
    from jsonschema import Draft202012Validator
except ImportError:  # 개발용 의존성(requirements-dev.txt). 없으면 판정 일치 검사는 건너뛴다.
    Draft202012Validator = None

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


def corpus():
    """스키마와 검증기가 같은 판정을 내리는지 볼 입력들. 경계 사례를 일부러 많이 넣는다."""
    docs = [
        good(), good(end="criteria met"), good(scope_changes=["a"]), good(artifacts=["a"], checks=["c"]),
        good(status="partial", evidence=[], unresolved=["x"]), good(status="blocked", evidence=[], unresolved=["x"]),
        good(status="partial", evidence=[{"path_or_url": "a", "check": "b"}], unresolved=["x"]),
        good(status="done"), good(status=None), good(result=5), good(result=""), good(result=True), good(evidence=[]),
        good(evidence=[{"path_or_url": "a"}]), good(evidence=[{"path_or_url": "a", "check": "b", "x": 1}]),
        good(evidence=[{"path_or_url": "", "check": "b"}]), good(evidence=["a"]), good(evidence=None),
        good(status="partial", evidence=[]), good(status="blocked", evidence=[], unresolved=[]),
        good(extra=1), good(artifacts="a.py"), good(artifacts=[""]), good(artifacts=[1]), good(checks=[""]),
        good(end="never"), good(end=None), good(end=""), good(unresolved=[""]), good(unresolved="x"),
        good(scope_changes=[""]), [], "completed", None, 5, True,
    ]
    for end in END_VALUES:
        docs.append(good(end=end))
    for key in ("status", "result", "evidence", "unresolved"):
        d = good()
        del d[key]
        docs.append(d)
    return docs


class SchemaFile(unittest.TestCase):
    def test_schema_is_valid_json_with_declared_dialect(self):
        s = load_schema()
        self.assertEqual(s["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(s["type"], "object")
        self.assertIs(s["additionalProperties"], False)

    def test_policy_example_matches_schema_fields(self):
        text = POLICY.read_text(encoding="utf-8")
        example = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))
        self.assertEqual(set(example), set(load_schema()["properties"]) - {"end", "scope_changes"})
        self.assertIn("output-contract.schema.json", text)
        self.assertEqual(validate({**example, "status": "completed", "result": "x",
                                   "evidence": [{"path_or_url": "p", "check": "c"}]}), [])

    def test_status_enum_matches_policy(self):
        text = POLICY.read_text(encoding="utf-8")
        for v in load_schema()["properties"]["status"]["enum"]:
            self.assertIn(v, text)

    def test_end_enum_matches_task_contract_end_field(self):
        text = POLICY.read_text(encoding="utf-8")
        for v in load_schema()["properties"]["end"]["enum"]:
            self.assertIn(v, text)

    def test_default_path(self):
        self.assertTrue(SCHEMA_PATH.is_file())


class ModelMatchesSchema(unittest.TestCase):
    """코드 모델(런타임 검증기)이 원본 스키마에서 벗어나지 않았는지 구조로 확인한다."""

    def test_field_names_match(self):
        self.assertEqual(set(Report.model_fields), set(load_schema()["properties"]))
        item = load_schema()["properties"]["evidence"]["items"]
        self.assertEqual(set(Evidence.model_fields), set(item["properties"]))

    def test_required_sets_match(self):
        s = load_schema()
        self.assertEqual({n for n, f in Report.model_fields.items() if f.is_required()}, set(s["required"]))
        item = s["properties"]["evidence"]["items"]
        self.assertEqual({n for n, f in Evidence.model_fields.items() if f.is_required()}, set(item["required"]))

    def test_enum_values_match(self):
        props = load_schema()["properties"]
        gen = Report.model_json_schema()["properties"]
        self.assertEqual(set(gen["status"]["enum"]), set(props["status"]["enum"]))
        self.assertEqual(set(gen["end"]["enum"]), set(props["end"]["enum"]))
        self.assertEqual(set(END_VALUES), set(props["end"]["enum"]))

    def test_closed_objects_match(self):
        s = load_schema()
        gen = Report.model_json_schema()
        self.assertIs(gen["additionalProperties"], False)
        self.assertIs(s["additionalProperties"], False)
        self.assertIs(s["properties"]["evidence"]["items"]["additionalProperties"], False)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema 가 없어 판정 일치 검사를 건너뜀")
    def test_verdicts_match_json_schema_on_corpus(self):
        v = Draft202012Validator(load_schema())
        diffs = [(i, d) for i, d in enumerate(corpus()) if bool(validate(d)) == v.is_valid(d)]
        self.assertEqual(diffs, [])

    def test_corpus_has_both_verdicts(self):
        results = [not validate(d) for d in corpus()]
        self.assertGreater(sum(results), 5)
        self.assertGreater(len(results) - sum(results), 20)


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

    def test_strict_mode_does_not_coerce(self):
        self.assertTrue(validate(good(result=5)))
        self.assertTrue(validate(good(result=True)))
        self.assertTrue(validate(good(artifacts=[1])))

    def test_explicit_null_for_optional_field_is_rejected(self):
        self.assertTrue(validate(good(end=None)))

    def test_completed_requires_evidence(self):
        self.assertTrue(validate(good(evidence=[])))

    def test_partial_and_blocked_require_unresolved(self):
        for st in ("partial", "blocked"):
            self.assertTrue(validate(good(status=st, evidence=[])), st)
            self.assertEqual(validate(good(status=st, evidence=[], unresolved=["needs X"])), [], st)

    def test_non_object_rejected(self):
        for bad in ([], "completed", None, 5):
            self.assertTrue(validate(bad), bad)

    def test_error_messages_carry_field_paths(self):
        errs = validate(good(evidence=[{"path_or_url": 3, "check": "b"}]))
        self.assertTrue(any(e.startswith("$.evidence[0].path_or_url:") for e in errs), errs)

    def test_validate_does_not_read_the_schema_file(self):
        with mock.patch.object(contract, "load_schema", side_effect=AssertionError("schema read")):
            for _ in range(3):
                self.assertEqual(validate(good()), [])


if __name__ == "__main__":
    unittest.main()
