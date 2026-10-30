"""하드 규칙 판정기의 단위 테스트. 합성 모델 능력만 사용하므로 실제 데이터 갱신과 무관하다."""
import unittest

from core.eligibility import rules as R
from core.eligibility import (ModelCaps, Route, Task, evaluate, plan_write_stages,
                              route_violations, scopes_overlap)


def caps(model, **kw):
    # 기본값은 강도 목록이 공개된 추론 선택형 모델이다. 다른 경우는 각 테스트 데이터가 명시적으로 덮어쓴다.
    base = dict(context_tokens=1_000_000, input_modalities=["text"], supports_tools=True,
                supports_reasoning=True, reasoning_mandatory=False, supported_efforts=["low", "high"],
                long_context_surcharge_tokens=None, free=False)
    base.update(kw)
    return ModelCaps.from_dict(model, base)


CAPS = {
    # 추론 필수 + 강도 목록 공개 (none 불가)
    "m/mandatory": caps("m/mandatory", reasoning_mandatory=True, supported_efforts=["high", "medium", "low"],
                        input_modalities=["text", "image"]),
    # 추론 선택 + 목록에 none 포함
    "m/optional": caps("m/optional", supported_efforts=["high", "low", "none"]),
    # 추론은 되지만 강도 목록 미공개
    "m/undisclosed": caps("m/undisclosed", supported_efforts=None, input_modalities=["text", "image", "audio"]),
    # 추론 기능 자체가 없음
    "m/noreason": caps("m/noreason", supports_reasoning=False),
    "m/free": caps("m/free", free=True),
    "m/paid": caps("m/paid"),
    "m/surcharge": caps("m/surcharge", long_context_surcharge_tokens=100_000, context_tokens=1_000_000),
    "m/small": caps("m/small", context_tokens=8_000),
    "m/notools": caps("m/notools", supports_tools=False),
}


def route(name, model, effort="low", tier="normal", fallback=()):
    return Route(name, model, effort, tier, tuple(fallback))


def check(r, routes=None, **kw):
    by = {x.name: x for x in (routes or [r])}
    return route_violations(r, CAPS, by, **kw)


class EffortRules(unittest.TestCase):
    def test_explicit_supported_effort_passes(self):
        self.assertEqual(check(route("a", "m/mandatory", "high")), [])

    def test_implicit_effort_is_rejected(self):
        self.assertEqual(check(route("a", "m/mandatory", None)), [R.EFFORT_IMPLICIT])

    def test_unlisted_effort_is_rejected(self):
        self.assertEqual(check(route("a", "m/mandatory", "xhigh")), [R.EFFORT_UNADVERTISED])

    def test_effort_is_rejected_when_model_does_not_disclose_efforts(self):
        # 목록이 공개되지 않은 모델에 강도를 지어내면 안 된다
        self.assertEqual(check(route("a", "m/undisclosed", "high")), [R.EFFORT_UNADVERTISED])

    def test_none_is_rejected_for_mandatory_reasoning(self):
        self.assertEqual(check(route("a", "m/mandatory", "none")), [R.EFFORT_CANNOT_DISABLE])

    def test_none_is_allowed_when_reasoning_is_optional(self):
        self.assertEqual(check(route("a", "m/optional", "none")), [])
        self.assertEqual(check(route("a", "m/undisclosed", "none")), [])

    def test_none_is_rejected_when_model_has_no_reasoning(self):
        self.assertEqual(check(route("a", "m/noreason", "none")), [R.EFFORT_CANNOT_DISABLE])


class ServiceTierRules(unittest.TestCase):
    def test_normal_passes_by_default(self):
        self.assertEqual(check(route("a", "m/optional", "low", "normal")), [])

    def test_fast_is_rejected_by_default(self):
        self.assertEqual(check(route("a", "m/optional", "low", "fast")), [R.SERVICE_TIER_UNVERIFIED])

    def test_missing_tier_is_rejected(self):
        self.assertEqual(check(route("a", "m/optional", "low", None)), [R.SERVICE_TIER_IMPLICIT])

    def test_extra_tier_can_be_allowed_explicitly(self):
        self.assertEqual(check(route("a", "m/optional", "low", "fast"), allowed_service_tiers={"normal", "fast"}), [])


class ModelAndFallbackRules(unittest.TestCase):
    def test_unknown_model_is_rejected_and_stops_other_checks(self):
        self.assertEqual(check(route("a", "m/ghost", None, None)), [R.UNKNOWN_MODEL])

    def test_free_route_with_paid_fallback_is_rejected(self):
        a = route("a", "m/free", "low", fallback=["b"])
        b = route("b", "m/paid", "low")
        self.assertEqual(check(a, [a, b]), [R.FREE_TO_PAID_FALLBACK])

    def test_free_route_with_free_fallback_is_allowed(self):
        a = route("a", "m/free", "low", fallback=["b"])
        b = route("b", "m/free", "low")
        self.assertEqual(check(a, [a, b]), [])

    def test_unknown_fallback_is_treated_as_paid(self):
        a = route("a", "m/free", "low", fallback=["missing"])
        self.assertEqual(check(a, [a]), [R.FREE_TO_PAID_FALLBACK])

    def test_paid_route_fallback_is_not_a_free_to_paid_case(self):
        a = route("a", "m/paid", "low", fallback=["b"])
        b = route("b", "m/paid", "low")
        self.assertEqual(check(a, [a, b]), [])


def decide(task, routes, registered=None, **kw):
    registered = [r.name for r in routes] if registered is None else registered
    return evaluate(task, routes, CAPS, registered=registered, **kw)


class TaskRules(unittest.TestCase):
    def test_unregistered_route_is_rejected(self):
        r = route("a", "m/optional", "low")
        d = decide(Task("t"), [r], registered=[])
        self.assertEqual(d.rejected["a"], (R.ROUTE_NOT_REGISTERED,))
        self.assertEqual(d.status, R.NEEDS_PARENT)

    def test_modality_missing_names_the_modality(self):
        r = route("a", "m/optional", "low")
        d = decide(Task("t", needs_modalities=frozenset({"text", "image"})), [r])
        self.assertEqual(d.rejected["a"], (f"{R.MODALITY_UNSUPPORTED}:image",))

    def test_multiple_missing_modalities_are_all_reported_in_order(self):
        r = route("a", "m/optional", "low")
        d = decide(Task("t", needs_modalities=frozenset({"video", "audio", "text"})), [r])
        self.assertEqual(d.rejected["a"], (f"{R.MODALITY_UNSUPPORTED}:audio", f"{R.MODALITY_UNSUPPORTED}:video"))

    def test_tools_required_but_unsupported(self):
        r = route("a", "m/notools", "low")
        self.assertEqual(decide(Task("t", needs_tools=True), [r]).rejected["a"], (R.TOOLS_UNSUPPORTED,))
        self.assertEqual(decide(Task("t", needs_tools=False), [r]).status, R.ELIGIBLE)

    def test_context_exceeded(self):
        r = route("a", "m/small", "low")
        self.assertEqual(decide(Task("t", input_tokens=8_001), [r]).rejected["a"], (R.CONTEXT_EXCEEDED,))
        self.assertEqual(decide(Task("t", input_tokens=8_000), [r]).status, R.ELIGIBLE)

    def test_surcharge_boundary_is_inclusive(self):
        r = route("a", "m/surcharge", "low")
        self.assertEqual(decide(Task("t", input_tokens=99_999), [r]).status, R.ELIGIBLE)
        self.assertEqual(decide(Task("t", input_tokens=100_000), [r]).rejected["a"], (R.LONG_CONTEXT_SURCHARGE,))

    def test_surcharge_can_be_accepted_explicitly(self):
        r = route("a", "m/surcharge", "low")
        d = decide(Task("t", input_tokens=500_000, allow_long_context_surcharge=True), [r])
        self.assertEqual(d.status, R.ELIGIBLE)

    def test_unknown_length_warns_but_does_not_reject(self):
        r = route("a", "m/surcharge", "low")
        d = decide(Task("t", input_tokens=None), [r])
        self.assertEqual(d.eligible, ("a",))
        self.assertEqual(d.warnings["a"], (R.WARN_LENGTH_UNKNOWN,))

    def test_no_warning_for_models_without_surcharge(self):
        r = route("a", "m/optional", "low")
        self.assertEqual(decide(Task("t", input_tokens=None), [r]).warnings, {})

    def test_reasons_accumulate(self):
        r = route("a", "m/mandatory", "none", "fast")
        d = decide(Task("t", needs_modalities=frozenset({"audio"})), [r])
        self.assertEqual(d.rejected["a"], (R.EFFORT_CANNOT_DISABLE, R.SERVICE_TIER_UNVERIFIED,
                                           f"{R.MODALITY_UNSUPPORTED}:audio"))


class DecisionStatus(unittest.TestCase):
    def setUp(self):
        self.routes = [route("ok", "m/optional", "low"), route("bad", "m/optional", None)]

    def test_eligible_keeps_input_order_and_lists_rejections(self):
        routes = [route("z", "m/optional", "low"), route("bad", "m/optional", None), route("a", "m/optional", "high")]
        d = decide(Task("t"), routes)
        self.assertEqual(d.status, R.ELIGIBLE)
        self.assertEqual(d.eligible, ("z", "a"))
        self.assertEqual(list(d.rejected), ["bad"])

    def test_no_eligible_route_goes_to_parent(self):
        d = decide(Task("t"), [route("bad", "m/optional", None)])
        self.assertEqual((d.status, d.eligible), (R.NEEDS_PARENT, ()))

    def test_approval_required_blocks_even_when_routes_are_eligible(self):
        d = decide(Task("t", requires_approval=True, approved=False), self.routes)
        self.assertEqual(d.status, R.NEEDS_APPROVAL)
        self.assertEqual(d.eligible, ("ok",))

    def test_approved_task_proceeds(self):
        d = decide(Task("t", requires_approval=True, approved=True), self.routes)
        self.assertEqual(d.status, R.ELIGIBLE)

    def test_high_risk_adds_review_flag_without_changing_eligibility(self):
        base = decide(Task("t"), self.routes)
        risky = decide(Task("t", high_risk=True), self.routes)
        self.assertEqual(risky.eligible, base.eligible)
        self.assertEqual(risky.rejected, base.rejected)
        self.assertEqual(risky.flags, ("independent_review",))
        self.assertEqual(base.flags, ())

    def test_high_risk_does_not_lift_approval_requirement(self):
        d = decide(Task("t", high_risk=True, requires_approval=True), self.routes)
        self.assertEqual(d.status, R.NEEDS_APPROVAL)


class WriteScopes(unittest.TestCase):
    def test_same_file_overlaps(self):
        self.assertTrue(scopes_overlap(["src/a.py"], ["src/a.py"]))

    def test_directory_contains_file(self):
        self.assertTrue(scopes_overlap(["src"], ["src/a.py"]))
        self.assertTrue(scopes_overlap(["src/a.py"], ["src/"]))

    def test_siblings_do_not_overlap(self):
        self.assertFalse(scopes_overlap(["src/a.py"], ["src/b.py"]))
        self.assertFalse(scopes_overlap(["src"], ["srcs/a.py"]))  # 접두 문자열이 같아도 다른 디렉터리

    def test_empty_scope_never_overlaps(self):
        self.assertFalse(scopes_overlap([], ["src/a.py"]))
        self.assertFalse(scopes_overlap([], []))

    def test_whole_tree_overlaps_everything(self):
        for root in (".", "/", "./"):
            self.assertTrue(scopes_overlap([root], ["src/a.py"]), root)

    def test_dot_dot_and_dot_segments_are_normalized(self):
        self.assertTrue(scopes_overlap(["src/../docs/x.md"], ["docs"]))
        self.assertTrue(scopes_overlap(["./src/a.py"], ["src/a.py"]))
        self.assertTrue(scopes_overlap(["src\\a.py"], ["src/a.py"]))

    def test_disjoint_tasks_share_a_stage(self):
        ts = [Task("a", write_scope=("x/a",)), Task("b", write_scope=("x/b",)), Task("r")]
        self.assertEqual(plan_write_stages(ts), [["a", "b", "r"]])

    def test_conflicting_tasks_are_serialized_in_order(self):
        ts = [Task("a", write_scope=("x",)), Task("b", write_scope=("x/f",)), Task("c", write_scope=("y",))]
        self.assertEqual(plan_write_stages(ts), [["a", "c"], ["b"]])

    def test_whole_tree_writer_runs_alone_against_other_writers(self):
        ts = [Task("a", write_scope=("x",)), Task("all", write_scope=(".",)), Task("ro")]
        self.assertEqual(plan_write_stages(ts), [["a", "ro"], ["all"]])

    def test_empty_input(self):
        self.assertEqual(plan_write_stages([]), [])


if __name__ == "__main__":
    unittest.main()
