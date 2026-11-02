"""CLI(typer) 동작 테스트. 값 검증은 pydantic 모델이 맡으므로 위반 입력이 종료 코드 2로 거부되는지 확인한다.

외부 네트워크와 실제 Hermes 설정을 쓰지 않는다(--apply 경로는 실행하지 않는다).
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from typer.testing import CliRunner

from adapters.hermes import apply_model_map, export_model_map, sync_plugin, sync_skill, validate_installed
from core.catalog import build_capabilities, inspect_endpoints

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = CliRunner()


def run(app, *args, **kw):
    return RUNNER.invoke(app, list(args), **kw)


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)

    def write(self, name, text):
        p = self.tmp / name
        p.write_text(text, encoding="utf-8")
        return p


class Help(unittest.TestCase):
    def test_every_cli_has_help(self):
        for mod in (build_capabilities, inspect_endpoints, apply_model_map, export_model_map,
                    sync_plugin, sync_skill, validate_installed):
            r = run(mod.app, "--help")
            self.assertEqual(r.exit_code, 0, mod.__name__)
            self.assertIn("Usage", r.output, mod.__name__)

    def test_no_completion_install_options(self):
        self.assertNotIn("--install-completion", run(inspect_endpoints.app, "--help").output)


class InspectEndpointsValidation(TempDirCase):
    def call(self, *args):
        return run(inspect_endpoints.app, *args)

    def test_requires_exactly_one_source(self):
        out = str(self.tmp / "o.json")
        specs = self.write("s.json", "[]")
        none = self.call("--out", out)
        both = self.call("--ids", "a/b", "--from-specs", str(specs), "--out", out)
        for r in (none, both):
            self.assertEqual(r.exit_code, 2, r.output)
            self.assertIn("정확히 하나", r.output)

    def test_ids_must_not_contain_whitespace(self):
        r = self.call("--ids", "a b", "--out", str(self.tmp / "o.json"))
        self.assertEqual(r.exit_code, 2)
        self.assertIn("--ids[0]", r.output)

    def test_positive_numbers_required(self):
        for flag in ("--timeout", "--workers"):
            r = self.call("--ids", "a/b", "--out", str(self.tmp / "o.json"), flag, "0")
            self.assertEqual(r.exit_code, 2, flag)
            self.assertIn(flag, r.output)

    def test_missing_specs_file_is_rejected_with_the_path(self):
        missing = self.tmp / "nope.json"
        r = self.call("--from-specs", str(missing), "--out", str(self.tmp / "o.json"))
        self.assertEqual(r.exit_code, 2)
        self.assertIn(str(missing), r.output)

    def test_space_separated_ids_are_not_supported(self):
        # 이전(argparse)에는 --ids a b c 가 통과했다. 이제 옵션을 반복해야 한다.
        r = self.call("--ids", "a/b", "c/d", "--out", str(self.tmp / "o.json"))
        self.assertEqual(r.exit_code, 2)
        self.assertIn("c/d", r.output)

    def test_out_is_required(self):
        self.assertEqual(self.call("--ids", "a/b").exit_code, 2)


class BuildCapabilitiesCli(TempDirCase):
    def files(self):
        specs = self.write("specs.json", json.dumps([{"name": "r1", "model": "x/y"}, {"name": "r2", "model": "x/y"}]))
        models = self.write("models.json", json.dumps({"data": [{"id": "x/y", "context_length": 1000, "other": 1}]}))
        return specs, models

    def test_offline_build_writes_sorted_capabilities(self):
        specs, models = self.files()
        out = self.tmp / "caps.json"
        r = run(build_capabilities.app, "--specs", str(specs), "--models-json", str(models), "--out", str(out),
                "--collected-at", "2026-01-02")
        self.assertEqual(r.exit_code, 0, r.output)
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["collected_at"], "2026-01-02")
        self.assertEqual(doc["source"]["file"], "models.json")
        self.assertEqual(list(doc["models"]), ["x/y"])
        self.assertEqual(doc["models"]["x/y"]["context_tokens"], 1000)
        self.assertTrue(out.read_text(encoding="utf-8").endswith("}\n"))

    def test_default_collected_at_is_today(self):
        import datetime

        specs, models = self.files()
        out = self.tmp / "caps.json"
        run(build_capabilities.app, "--specs", str(specs), "--models-json", str(models), "--out", str(out))
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["collected_at"], datetime.date.today().isoformat())

    def test_invalid_date_is_rejected(self):
        specs, models = self.files()
        r = run(build_capabilities.app, "--specs", str(specs), "--models-json", str(models),
                "--out", str(self.tmp / "o.json"), "--collected-at", "2026-13-45")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("--collected-at", r.output)

    def test_missing_input_files_and_bad_timeout_are_rejected(self):
        specs, models = self.files()
        out = str(self.tmp / "o.json")
        self.assertEqual(run(build_capabilities.app, "--specs", str(self.tmp / "x"), "--out", out).exit_code, 2)
        self.assertEqual(run(build_capabilities.app, "--specs", str(specs), "--models-json", str(self.tmp / "x"),
                             "--out", out).exit_code, 2)
        r = run(build_capabilities.app, "--specs", str(specs), "--models-json", str(models), "--out", out,
                "--timeout", "0")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("--timeout", r.output)

    def test_model_missing_from_listing_fails(self):
        specs, _ = self.files()
        models = self.write("m2.json", json.dumps({"data": [{"id": "other/model"}]}))
        r = run(build_capabilities.app, "--specs", str(specs), "--models-json", str(models), "--out", str(self.tmp / "o.json"))
        self.assertEqual(r.exit_code, 1)
        self.assertIn("x/y", r.output)


class ExportModelMapCli(TempDirCase):
    def test_check_passes_on_the_repo(self):
        r = run(export_model_map.app, "--check")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("OK", r.output)

    def test_check_reports_drift_and_does_not_write(self):
        stale = self.write("stale.json", "{}\n")
        r = run(export_model_map.app, "--check", "--out", str(stale))
        self.assertEqual(r.exit_code, 1)
        self.assertIn("DRIFT", r.output)
        self.assertEqual(stale.read_text(encoding="utf-8"), "{}\n")

    def test_writes_the_same_bytes_as_the_committed_file(self):
        out = self.tmp / "regen.json"
        r = run(export_model_map.app, "--out", str(out))
        self.assertEqual(r.exit_code, 0, r.output)
        committed = ROOT / "adapters" / "hermes" / "model-map-proposal.json"
        self.assertEqual(out.read_bytes(), committed.read_bytes())

    def test_missing_specs_is_rejected(self):
        r = run(export_model_map.app, "--specs", str(self.tmp / "nope.json"))
        self.assertEqual(r.exit_code, 2)


class SyncCli(TempDirCase):
    def test_checks_pass_on_the_repo(self):
        for mod in (sync_plugin, sync_skill):
            r = run(mod.app, "--check")
            self.assertEqual(r.exit_code, 0, f"{mod.__name__}: {r.output}")

    def sandbox(self, mod):
        src, dst = self.write("src.txt", "new"), self.tmp / "out" / "dst.txt"
        return mock.patch.multiple(mod, ROOT=self.tmp, MAPPING={src: dst}), src, dst

    def test_check_detects_drift_without_writing_then_sync_fixes_it(self):
        for mod in (sync_plugin, sync_skill):
            patch, src, dst = self.sandbox(mod)
            with patch:
                r = run(mod.app, "--check")
                self.assertEqual(r.exit_code, 1, mod.__name__)
                self.assertIn("DRIFT", r.output)
                self.assertFalse(dst.exists())
                self.assertEqual(run(mod.app).exit_code, 0)
                self.assertEqual(dst.read_text(encoding="utf-8"), "new")
                self.assertEqual(run(mod.app, "--check").exit_code, 0)
            dst.unlink()
            dst.parent.rmdir()


class ValidateInstalledCli(TempDirCase):
    def test_hermes_home_is_required(self):
        r = run(validate_installed.app, env={"HERMES_HOME": ""})
        self.assertEqual(r.exit_code, 2)
        self.assertIn("HERMES_HOME", r.output)

    def test_hermes_home_must_be_a_directory(self):
        r = run(validate_installed.app, "--hermes-home", str(self.tmp / "missing"))
        self.assertEqual(r.exit_code, 2)
        self.assertIn("--hermes-home", r.output)

    def test_env_var_is_used_when_the_option_is_absent(self):
        with mock.patch.object(validate_installed, "run", return_value={"checks": [], "passed": 0, "count": 0}) as m:
            r = run(validate_installed.app, env={"HERMES_HOME": str(self.tmp)})
        self.assertEqual(r.exit_code, 0, r.output)
        m.assert_called_once_with(self.tmp)

    def test_failed_probe_exits_nonzero_and_writes_result(self):
        result = {"checks": [{"name": "a", "passed": False}], "passed": 0, "count": 1}
        out = self.tmp / "r.json"
        with mock.patch.object(validate_installed, "run", return_value=result):
            r = run(validate_installed.app, "--hermes-home", str(self.tmp), "--out", str(out))
        self.assertEqual(r.exit_code, 1)
        self.assertIn("FAIL a", r.output)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["count"], 1)


class ApplyModelMapCli(unittest.TestCase):
    def test_restart_requires_apply(self):
        r = run(apply_model_map.app, "--restart")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("--apply", r.output)

    def test_restart_all_requires_restart(self):
        r = run(apply_model_map.app, "--apply", "--restart-all")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("--restart", r.output)

    def test_default_run_validates_and_writes_nothing(self):
        with mock.patch.object(apply_model_map, "hermes_exe", side_effect=AssertionError("must not run")):
            r = run(apply_model_map.app)
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("검증 통과", r.output)
        self.assertIn("아무것도 쓰지 않았습니다", r.output)

    def test_print_yaml_outputs_the_block(self):
        data = apply_model_map.load(apply_model_map.PROPOSAL)
        r = run(apply_model_map.app, "--print-yaml")
        self.assertEqual(r.exit_code, 0)
        self.assertEqual(r.output, apply_model_map.yaml_block(data["options"], data["default"]))

    def test_short_flags_are_accepted(self):
        r = run(apply_model_map.app, "-p", "biser", "-y")
        self.assertEqual(r.exit_code, 0, r.output)

    def test_missing_proposal_is_rejected(self):
        r = run(apply_model_map.app, "--proposal", "/nonexistent/p.json")
        self.assertEqual(r.exit_code, 2)


class ApplyModelMapApplyPath(TempDirCase):
    """--apply 이하의 경로를 hermes 호출을 가짜로 대체해 검증한다(실제 설정과 실행 파일은 건드리지 않는다)."""

    def setUp(self):
        super().setUp()
        self.cfg = self.write("config.yaml", "existing: true\n")
        self.calls = []

    def fake_run(self, *, fail_set=False, readback=True, fail_restart=False):
        def run_(exe, profile, args, timeout=180):
            self.calls.append((profile, tuple(args[:2])))
            if args[:2] == ["config", "set"]:
                return (3, "boom") if fail_set else (0, "")
            if args[:2] == ["config", "get"]:
                text = "model_map " + " ".join(o["name"] for o in apply_model_map.load(apply_model_map.PROPOSAL)["options"])
                return 0, (text + " M-Haiku-Balanced") if readback else ""
            if args[:2] == ["gateway", "restart"]:
                return (4, "restart failed") if fail_restart else (0, "restarted")
            return 0, "running"
        return run_

    def apply(self, *flags, **fake):
        patches = [mock.patch.object(apply_model_map, "hermes_exe", return_value="hermes"),
                   mock.patch.object(apply_model_map, "run", self.fake_run(**fake)),
                   mock.patch.object(apply_model_map.time, "sleep")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return run(apply_model_map.app, "--apply", "--config", str(self.cfg), *flags, input="")

    def backups(self):
        return [p for p in self.tmp.iterdir() if "before-model-map" in p.name]

    def test_success_backs_up_sets_twice_and_verifies(self):
        r = self.apply(readback=True)
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(self.backups()[0].read_text(encoding="utf-8"), "existing: true\n")
        self.assertEqual([c[1] for c in self.calls].count(("config", "set")), 2)
        self.assertIn("read-back 확인", r.output)

    def test_set_failure_stops_after_the_first_call_and_points_to_the_backup(self):
        r = self.apply(fail_set=True)
        self.assertEqual(r.exit_code, 1)
        self.assertEqual([c[1] for c in self.calls].count(("config", "set")), 1)
        self.assertIn("백업으로 되돌리십시오", r.output)

    def test_readback_mismatch_exits_nonzero(self):
        r = self.apply(readback=False)
        self.assertEqual(r.exit_code, 1)
        self.assertIn("read-back 불일치", r.output)

    def test_restart_with_yes_runs_and_reports(self):
        r = self.apply("--restart", "-y")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn(("", ("gateway", "restart")), self.calls)

    def test_restart_failure_exits_nonzero(self):
        r = self.apply("--restart", "-y", fail_restart=True)
        self.assertEqual(r.exit_code, 1)
        self.assertIn("재시작 확인에 실패", r.output)

    def test_restart_without_confirmation_is_skipped(self):
        r = self.apply("--restart")  # 입력이 비어 있으면(EOF) 재시작하지 않는다
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertNotIn(("", ("gateway", "restart")), self.calls)
        self.assertIn("재시작을 생략했습니다", r.output)

    def test_profile_is_passed_to_every_hermes_call(self):
        self.apply("-p", "biser")
        self.assertTrue(self.calls)
        self.assertEqual({c[0] for c in self.calls}, {"biser"})


if __name__ == "__main__":
    unittest.main()
