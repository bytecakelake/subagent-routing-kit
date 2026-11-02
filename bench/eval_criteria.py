#!/usr/bin/env python3
"""속도 외 기준으로 후보 라이브러리를 검증한다. 실험 브랜치 전용.

실행: <venv>/bin/python bench/eval_criteria.py [--out bench/criteria-results.json]
각 섹션은 '사실'(관찰된 동작)만 기록한다. 판단은 docs/library-candidates-experiment.md 에 쓴다.
"""
import http.server
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Annotated

import typer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = {}

from core import cliutil  # noqa: E402
from core.contract import load_schema  # noqa: E402
from core.contract import validate as pydantic_validate  # noqa: E402


# ---------- A. orjson: 바이트 호환성과 의미 차이 ----------
def eval_orjson():
    import orjson

    res = {"byte_identical_files": {}, "edge_cases": {}}
    files = sorted((ROOT / "core" / "spec").glob("*.json")) + [ROOT / "adapters" / "hermes" / "model-map-proposal.json"]
    for p in files:
        raw = p.read_bytes()
        obj = json.loads(raw)
        std = (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode()
        ora = orjson.dumps(obj, option=orjson.OPT_INDENT_2) + b"\n"
        res["byte_identical_files"][p.name] = {"file_matches_stdlib_dump": raw == std, "orjson_matches_stdlib_dump": ora == std, "file_matches_orjson_dump": raw == ora}

    def case(label, value, **kw):
        r = {}
        try:
            r["json"] = json.dumps(value, **kw)
        except Exception as e:
            r["json"] = f"ERR {type(e).__name__}: {e}"
        try:
            r["orjson"] = orjson.dumps(value).decode()
        except Exception as e:
            r["orjson"] = f"ERR {type(e).__name__}: {e}"
        r["same"] = r["json"] == r["orjson"]
        for k in ("json", "orjson"):
            r[k] = r[k].encode("utf-8", "backslashreplace").decode("utf-8")  # 단독 서로게이트도 기록 가능하게
        res["edge_cases"][label] = r

    case("korean_text", {"a": "한글"}, ensure_ascii=False, separators=(",", ":"))
    case("float_0.1+0.2", 0.1 + 0.2, separators=(",", ":"))
    case("float_1e22", 1e22, separators=(",", ":"))
    case("float_1e16", 1e16, separators=(",", ":"))
    case("int_2**70", 2**70, separators=(",", ":"))
    case("nan", float("nan"), separators=(",", ":"))
    case("neg_zero", -0.0, separators=(",", ":"))
    case("int_key", {1: "a"}, separators=(",", ":"))
    case("tuple", (1, 2), separators=(",", ":"))
    case("frozenset", frozenset({1}), separators=(",", ":"))
    case("lone_surrogate", "\ud800", ensure_ascii=False, separators=(",", ":"))
    for label, text in [("dup_keys", '{"a":1,"a":2}'), ("nan_literal", '[NaN]'), ("big_int", "123456789012345678901234567890")]:
        r = {}
        for name, fn in (("json", json.loads), ("orjson", orjson.loads)):
            try:
                r[name] = repr(fn(text))
            except Exception as e:
                r[name] = f"ERR {type(e).__name__}"
        r["same"] = r["json"] == r["orjson"]
        res["edge_cases"]["loads:" + label] = r
    res["dumps_return_type"] = type(orjson.dumps({})).__name__
    OUT["orjson"] = res


# ---------- B. 스키마 검증 라이브러리: 문법 범위와 오류 메시지 ----------
def eval_schema_libs():
    import fastjsonschema
    import jsonschema
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import best_match

    schema = load_schema()
    bad = {
        "wrong_status": {"status": "done", "result": "ok", "evidence": [{"path_or_url": "a", "check": "b"}], "unresolved": []},
        "completed_without_evidence": {"status": "completed", "result": "ok", "evidence": [], "unresolved": []},
        "blocked_without_unresolved": {"status": "blocked", "result": "ok", "evidence": [], "unresolved": []},
        "extra_field": {"status": "completed", "result": "ok", "evidence": [{"path_or_url": "a", "check": "b"}], "unresolved": [], "x": 1},
        "missing_field": {"status": "completed", "result": "ok", "unresolved": []},
        "nested_type": {"status": "completed", "result": "ok", "evidence": [{"path_or_url": 3, "check": "b"}], "unresolved": []},
    }
    msgs = {}
    for k, doc in bad.items():
        row = {"pydantic(core.contract)": pydantic_validate(doc)}
        v = Draft202012Validator(schema)
        errs = sorted(v.iter_errors(doc), key=lambda e: list(e.path))
        row["jsonschema_all"] = [e.message[:140] for e in errs]
        row["jsonschema_best_match"] = best_match(v.iter_errors(doc)).message[:140]
        try:
            fastjsonschema.compile(schema)(doc)
            row["fastjsonschema"] = "PASSED(!)"
        except fastjsonschema.JsonSchemaException as e:
            row["fastjsonschema"] = e.message[:140]
        msgs[k] = row
    # 문법 범위: 라이브러리가 JSON Schema 키워드를 올바르게 처리하는지
    probes = {
        "pattern": ({"type": "string", "pattern": "^[a-z]+$"}, "abc", "ABC"),
        "format_date": ({"type": "string", "format": "date"}, "2026-10-30", "x"),
        "$ref": ({"$defs": {"s": {"type": "string"}}, "$ref": "#/$defs/s"}, "a", 1),
        "oneOf": ({"oneOf": [{"type": "string"}, {"type": "integer"}]}, 1, None),
        "uniqueItems": ({"type": "array", "uniqueItems": True}, [1, 2], [1, 1]),
        "maximum": ({"type": "integer", "maximum": 3}, 3, 4),
        "dependentRequired": ({"dependentRequired": {"a": ["b"]}}, {"a": 1, "b": 2}, {"a": 1}),
    }
    cover = {}
    for k, (s, good, badv) in probes.items():
        row = {}
        v = Draft202012Validator(s, format_checker=jsonschema.FormatChecker())
        row["jsonschema(good,bad)"] = (v.is_valid(good), v.is_valid(badv))
        try:
            f = fastjsonschema.compile(s)
            f(good)
            try:
                f(badv)
                row["fastjsonschema(good,bad)"] = "good ok, bad ALSO PASSED"
            except fastjsonschema.JsonSchemaException:
                row["fastjsonschema(good,bad)"] = "good ok, bad rejected"
        except Exception as e:
            row["fastjsonschema(good,bad)"] = f"ERR {type(e).__name__}: {str(e)[:80]}"
        cover[k] = row
    OUT["schema_libs"] = {"error_messages": msgs, "keyword_coverage": cover}


# ---------- C. httpx vs urllib: 동작 차이 (로컬 서버로 재현) ----------
class H(http.server.BaseHTTPRequestHandler):
    flaky = {"n": 0}

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/ok":
            self._send(200, b'{"ok":true}')
        elif self.path == "/404":
            self._send(404, b'{"error":"nf"}')
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
        elif self.path == "/slow":
            time.sleep(3)
            self._send(200, b"late")
        elif self.path == "/flaky":
            H.flaky["n"] += 1
            self._send(500 if H.flaky["n"] <= 2 else 200, b"x")
        elif self.path == "/429":
            self.send_response(429)
            self.send_header("Retry-After", "1")
            self.send_header("Content-Length", "0")
            self.end_headers()

    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def eval_http():
    import httpx

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    res = {}

    def u(path, timeout=5):
        try:
            with urllib.request.urlopen(base + path, timeout=timeout) as r:
                return f"status={r.status} body={r.read()[:20]!r}"
        except urllib.error.HTTPError as e:
            return f"raises HTTPError {e.code}"
        except Exception as e:
            return f"raises {type(e).__name__}"

    c = httpx.Client(timeout=5)

    def h(path, **kw):
        try:
            r = c.get(base + path, **kw)
            return f"status={r.status_code} body={r.content[:20]!r}"
        except Exception as e:
            return f"raises {type(e).__name__}"

    for path in ("/ok", "/404", "/redirect", "/429"):
        res[path] = {"urllib": u(path), "httpx(default)": h(path)}
    res["/redirect"]["httpx(follow_redirects=True)"] = h("/redirect", follow_redirects=True)
    res["/slow timeout=1"] = {"urllib": u("/slow", 1)}
    try:
        httpx.Client(timeout=1).get(base + "/slow")
        res["/slow timeout=1"]["httpx"] = "no error"
    except Exception as e:
        res["/slow timeout=1"]["httpx"] = f"raises {type(e).__name__}"
    # 재시도: httpx 의 transport retries 는 연결 오류만 재시도한다. 500 은 재시도하지 않는다.
    H.flaky["n"] = 0
    tr = httpx.HTTPTransport(retries=3)
    with httpx.Client(transport=tr, timeout=5) as rc:
        res["/flaky (500,500,200) httpx retries=3"] = f"status={rc.get(base + '/flaky').status_code}, server hits={H.flaky['n']}"
    H.flaky["n"] = 0
    try:
        with httpx.Client(timeout=5) as rc:
            r = rc.get(base + "/flaky")
            r.raise_for_status()
    except httpx.HTTPStatusError as e:
        res["/flaky raise_for_status"] = f"HTTPStatusError {e.response.status_code}"
    # 연결 재사용: 같은 서버로 20회 요청 소요 시간
    t = time.perf_counter()
    for _ in range(20):
        u("/ok")
    t_u = time.perf_counter() - t
    t = time.perf_counter()
    for _ in range(20):
        c.get(base + "/ok")
    t_h = time.perf_counter() - t
    res["20 sequential local requests (ms)"] = {"urllib": round(t_u * 1e3, 1), "httpx(client reuse)": round(t_h * 1e3, 1)}
    # 요청 헤더: urllib 은 User-Agent 를 Python-urllib 으로 보낸다
    res["http2_extra"] = "h2 not installed" if not _have("h2") else "h2 installed"
    srv.shutdown()
    OUT["http"] = res


def _have(m):
    try:
        __import__(m)
        return True
    except ImportError:
        return False


# ---------- D. pydantic: core.contract 의 실제 구현을 평가 ----------
def eval_pydantic():
    from jsonschema import Draft202012Validator

    from core import contract
    from tests.test_output_contract import corpus as test_corpus

    committed = Draft202012Validator(load_schema())
    docs = test_corpus()
    res = {"corpus_size": len(docs)}
    verdicts = [(not contract.validate(d), committed.is_valid(d)) for d in docs]
    res["pydantic_vs_committed_schema_disagreements"] = [i for i, (a, b) in enumerate(verdicts) if a != b]
    # 반대 방향: pydantic 이 생성한 스키마를 쓰면 무엇이 사라지는가
    gen = contract.Report.model_json_schema()
    gv = Draft202012Validator(gen)
    lost = [i for i, d in enumerate(docs) if gv.is_valid(d) and contract.validate(d)]
    res["generated_schema_accepts_what_model_rejects(corpus idx)"] = lost
    res["generated_schema_has_conditional_rules"] = any(k in gen for k in ("allOf", "if", "oneOf", "anyOf"))
    res["generated_required_equals_committed"] = gen["required"] == load_schema()["required"]
    res["generated_uses_$defs_ref"] = "$defs" in gen
    # lax 모드 대비: 같은 입력을 lax 로 검증하면 통과하는가
    from pydantic import BaseModel, ConfigDict, ValidationError

    class Lax(BaseModel):
        model_config = ConfigDict(extra="forbid")
        result: str
        n: int = 0

    def lax_ok(d):
        try:
            Lax.model_validate(d)
            return True
        except ValidationError:
            return False

    res["lax_vs_strict"] = {"result=5 (strict rejects)": lax_ok({"result": 5}), "n='5'": lax_ok({"result": "x", "n": "5"}), "n=True": lax_ok({"result": "x", "n": True})}
    res["sample_error_style"] = contract.validate({"status": "done"})
    OUT["pydantic"] = res


# ---------- E. pytest: 기존 테스트 호환성과 실패 출력 ----------
def eval_pytest():
    res = {}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=ROOT, capture_output=True, text=True)
    res["existing_unittest_suite_unmodified"] = r.stdout.strip().splitlines()[-1]
    with tempfile.TemporaryDirectory() as d:
        t = pathlib.Path(d) / "test_fail.py"
        t.write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_dict(self):\n"
            "        self.assertEqual({'status': 'blocked', 'unresolved': ['a'], 'x': 1}, {'status': 'blocked', 'unresolved': ['b'], 'x': 1})\n"
            "def test_plain():\n"
            "    got = {'status': 'blocked', 'unresolved': ['a'], 'x': 1}\n"
            "    assert got == {'status': 'blocked', 'unresolved': ['b'], 'x': 1}\n",
            encoding="utf-8",
        )
        u = subprocess.run([sys.executable, "-m", "unittest", str(t)], capture_output=True, text=True, cwd=d)
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(t)], capture_output=True, text=True, cwd=d)
        res["failure_output_lines"] = {"unittest": len(u.stderr.splitlines()), "pytest": len(p.stdout.splitlines())}
        res["unittest_failure_excerpt"] = u.stderr.strip().splitlines()[3:12]
        res["pytest_failure_excerpt"] = [l for l in p.stdout.splitlines() if l.startswith(("E ", "E\t")) or "Differing" in l][:10]
    r = subprocess.run([sys.executable, "-m", "pytest", "--version"], capture_output=True, text=True)
    res["xdist_installed"] = _have("xdist")
    OUT["pytest"] = res


app = cliutil.make_app()


@app.command(help=__doc__)
def main(
    out: Annotated[pathlib.Path, typer.Option(help="결과 JSON 저장 경로")] = ROOT / "bench" / "criteria-results.json",
):
    for fn in (eval_orjson, eval_schema_libs, eval_http, eval_pydantic, eval_pytest):
        try:
            fn()
        except Exception as e:  # 한 섹션의 실패가 나머지를 막지 않게 한다
            OUT[fn.__name__] = {"ERROR": f"{type(e).__name__}: {e}"}
    out.write_text(json.dumps(OUT, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(OUT, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
