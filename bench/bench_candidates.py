#!/usr/bin/env python3
"""표준 라이브러리 대비 후보 라이브러리 비교 측정. 실험 브랜치 전용이며 core/ 는 건드리지 않는다.

실행: <venv>/bin/python bench/bench_candidates.py [--out bench/results.json] [--no-network]
후보가 설치돼 있지 않으면 해당 항목만 건너뛴다.
"""
import argparse
import asyncio
import concurrent.futures
import importlib
import json
import pathlib
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.contract import load_schema, validate  # noqa: E402
from core.eligibility import Task  # noqa: E402

SPEC_DIR = ROOT / "core" / "spec"
OUT = {}


def have(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def bench(fn, n, repeat=7):
    """호출당 마이크로초의 중앙값과 최솟값."""
    runs = []
    for _ in range(repeat):
        t = time.perf_counter()
        for _ in range(n):
            fn()
        runs.append((time.perf_counter() - t) / n * 1e6)
    return {"median_us": round(statistics.median(runs), 2), "min_us": round(min(runs), 2)}


# ---------- 1. JSON ----------
def section_json(models_blob):
    orjson = have("orjson")
    res = {}
    files = {p.name: p.read_bytes() for p in sorted(SPEC_DIR.glob("*.json"))}
    for label, blob in [("spec_all_files", None), ("variant-specs.json", files["variant-specs.json"])] + (
        [("models_api_snapshot", models_blob)] if models_blob else []
    ):
        blobs = list(files.values()) if blob is None else [blob]
        size = sum(map(len, blobs))
        r = {"bytes": size, "json.loads": bench(lambda: [json.loads(b) for b in blobs], 200 if size < 1e5 else 10)}
        if orjson:
            r["orjson.loads"] = bench(lambda: [orjson.loads(b) for b in blobs], 200 if size < 1e5 else 10)
        res[label] = r
    OUT["json"] = res


# ---------- 2. 스키마 검증 ----------
def corpus():
    ok = {"status": "completed", "result": "ok", "evidence": [{"path_or_url": "a", "check": "b"}], "unresolved": []}

    def v(**o):
        d = json.loads(json.dumps(ok))
        d.update(o)
        return d

    docs = [
        v(), v(end="criteria met"), v(status="partial", evidence=[], unresolved=["x"]),
        v(status="blocked", evidence=[], unresolved=["x"]), v(scope_changes=["a"]), v(artifacts=["a"], checks=["c"]),
        v(status="done"), v(result=5), v(result=""), v(evidence=[]), v(evidence=[{"path_or_url": "a"}]),
        v(status="partial", evidence=[]), v(status="blocked", evidence=[], unresolved=[]), v(extra=1),
        v(artifacts="a.py"), v(end="never"), v(unresolved=[""]), [], "completed", None,
    ]
    for k in ("status", "result", "evidence", "unresolved"):
        d = v()
        del d[k]
        docs.append(d)
    return docs


def section_schema():
    schema = load_schema()
    docs = corpus()
    own = [not validate(d, schema) for d in docs]
    res = {"corpus_size": len(docs), "valid_in_corpus": sum(own)}
    res["own_validator(preloaded)"] = bench(lambda: [validate(d, schema) for d in docs], 100)
    js = have("jsonschema")
    if js:
        from jsonschema import Draft202012Validator
        v = Draft202012Validator(schema)
        theirs = [v.is_valid(d) for d in docs]
        res["jsonschema_agrees"] = own == theirs
        res["jsonschema_disagreements"] = [i for i, (a, b) in enumerate(zip(own, theirs)) if a != b]
        res["jsonschema(prebuilt)"] = bench(lambda: [v.is_valid(d) for d in docs], 100)
    fj = have("fastjsonschema")
    if fj:
        f = fj.compile(schema)

        def ok(d):
            try:
                f(d)
                return True
            except fj.JsonSchemaException:
                return False

        theirs = [ok(d) for d in docs]
        res["fastjsonschema_agrees"] = own == theirs
        res["fastjsonschema_disagreements"] = [i for i, (a, b) in enumerate(zip(own, theirs)) if a != b]
        res["fastjsonschema(compiled)"] = bench(lambda: [ok(d) for d in docs], 100)
    OUT["schema_validation"] = res


# ---------- 3. 데이터 모델 ----------
def section_model():
    res = {"dataclass(frozen)": bench(lambda: Task("t", input_tokens=1000, needs_tools=True), 20000)}
    pyd = have("pydantic")
    if pyd:
        from pydantic import BaseModel, ConfigDict

        class PTask(BaseModel):
            model_config = ConfigDict(frozen=True)
            id: str
            input_tokens: int | None = None
            needs_modalities: frozenset = frozenset({"text"})
            needs_tools: bool = False
            allow_long_context_surcharge: bool = False
            requires_approval: bool = False

        res["pydantic.BaseModel(frozen)"] = bench(lambda: PTask(id="t", input_tokens=1000, needs_tools=True), 20000)
        res["pydantic.model_validate(dict)"] = bench(lambda: PTask.model_validate({"id": "t", "input_tokens": 1000}), 20000)
    OUT["data_model"] = res


# ---------- 4. 프로세스 기동 / import 비용 ----------
def startup(stmt, n=15):
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        subprocess.run([sys.executable, "-c", stmt], check=True, capture_output=True)
        ts.append((time.perf_counter() - t) * 1e3)
    return {"median_ms": round(statistics.median(ts), 1), "min_ms": round(min(ts), 1)}


def section_startup():
    res = {"python -c pass": startup("pass")}
    for label, stmt in [
        ("import json,urllib.request,argparse (stdlib)", "import json,urllib.request,argparse"),
        ("import orjson", "import orjson"),
        ("import jsonschema", "import jsonschema"),
        ("import fastjsonschema", "import fastjsonschema"),
        ("import httpx", "import httpx"),
        ("import pydantic", "import pydantic"),
        ("import typer", "import typer"),
    ]:
        mod = stmt.split()[-1].split(",")[0]
        if label.startswith("import ") and "(stdlib)" not in label and not have(mod):
            continue
        res[label] = startup(stmt)
    OUT["startup_import_cost"] = res


# ---------- 5. 테스트 러너 ----------
def section_runners():
    res = {}
    t = time.perf_counter()
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=ROOT, capture_output=True, text=True)
    res["unittest"] = {"seconds": round(time.perf_counter() - t, 2), "tail": r.stderr.strip().splitlines()[-1]}
    if have("pytest"):
        t = time.perf_counter()
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=ROOT, capture_output=True, text=True)
        res["pytest"] = {"seconds": round(time.perf_counter() - t, 2), "tail": r.stdout.strip().splitlines()[-1]}
    OUT["test_runners"] = res


# ---------- 6. 네트워크 ----------
def section_network(workers=6, rounds=3):
    ids = []
    for s in json.loads((SPEC_DIR / "variant-specs.json").read_text(encoding="utf-8")):
        if s["model"] not in ids:
            ids.append(s["model"])
    urls = ["https://openrouter.ai/api/v1/models/" + urllib.parse.quote(i, safe="/:") + "/endpoints" for i in ids]
    res = {"urls": len(urls)}

    def u_fetch(url):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return len(r.read())
        except Exception as e:
            return f"ERR {type(e).__name__}"

    def run_urllib():
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(u_fetch, urls))

    def timed(fn):
        ts, last = [], None
        for _ in range(rounds):
            t = time.perf_counter()
            last = fn()
            ts.append(time.perf_counter() - t)
        errs = sum(isinstance(x, str) for x in last)
        return {"median_s": round(statistics.median(ts), 2), "min_s": round(min(ts), 2), "errors": errs, "bytes": sum(x for x in last if isinstance(x, int))}

    res["urllib+ThreadPool(6)"] = timed(run_urllib)
    httpx = have("httpx")
    if httpx:
        def run_httpx_sync():
            with httpx.Client(timeout=40, http2=False) as c, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                def f(url):
                    try:
                        return len(c.get(url).content)
                    except Exception as e:
                        return f"ERR {type(e).__name__}"
                return list(ex.map(f, urls))

        async def _async():
            sem = asyncio.Semaphore(workers)
            async with httpx.AsyncClient(timeout=40) as c:
                async def f(url):
                    async with sem:
                        try:
                            return len((await c.get(url)).content)
                        except Exception as e:
                            return f"ERR {type(e).__name__}"
                return await asyncio.gather(*(f(u) for u in urls))

        res["httpx.Client+ThreadPool(6)"] = timed(run_httpx_sync)
        res["httpx.AsyncClient(sem 6)"] = timed(lambda: asyncio.run(_async()))
    OUT["network"] = res


def fetch_models_blob():
    try:
        with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=60) as r:
            return r.read()
    except Exception as e:
        OUT["models_snapshot_error"] = f"{type(e).__name__}: {e}"
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "bench" / "results.json"))
    ap.add_argument("--no-network", action="store_true")
    a = ap.parse_args()
    OUT["python"] = sys.version.split()[0]
    from importlib.metadata import version

    OUT["installed"] = {m: version(m) for m in ("orjson", "jsonschema", "fastjsonschema", "httpx", "pydantic", "pytest", "typer") if have(m)}
    blob = None if a.no_network else fetch_models_blob()
    section_json(blob)
    section_schema()
    section_model()
    section_startup()
    section_runners()
    if not a.no_network:
        section_network()
    pathlib.Path(a.out).write_text(json.dumps(OUT, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(OUT, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
