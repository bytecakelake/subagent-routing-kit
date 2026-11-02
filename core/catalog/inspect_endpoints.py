#!/usr/bin/env python3
"""OpenRouter 모델의 엔드포인트(가격, 지원 파라미터, 컨텍스트, 상태)를 조회해 JSON으로 저장한다.

정확한 모델 ID(`:free` 같은 접미사 포함)로 /api/v1/models/{id}/endpoints 를 직접 조회한다.
모델 목록 스냅샷의 links.details 는 `:free` 접미사를 떼어 유료 엔드포인트를 돌려줄 수 있어 사용하지 않는다.
공개 API만 읽으며 인증 키가 필요 없다. orjson 과 httpx 를 사용한다(requirements.txt).

예:
  python inspect_endpoints.py --from-specs ../spec/variant-specs.json --out endpoints.json
  python inspect_endpoints.py --ids openai/gpt-6-luna nvidia/nemotron-3.5-super-vl:free --out endpoints.json
"""
import argparse
import concurrent.futures
import pathlib
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # 스크립트로 직접 실행해도 core 를 import 할 수 있게 한다

from core import jsonio  # noqa: E402
from core.catalog import _http  # noqa: E402

BASE = "https://openrouter.ai/api/v1/models/"


def ids_from_specs(path):
    specs = jsonio.load_path(path)
    seen = []
    for s in specs:
        if s["model"] not in seen:
            seen.append(s["model"])
    return seen


def fetch(client, model_id):
    # 슬래시는 경로 구분자로 유지하고 ':' 는 그대로 보낸다.
    url = BASE + urllib.parse.quote(model_id, safe="/:") + "/endpoints"
    try:
        return {"id": model_id, "url": url, "response": jsonio.loads(_http.get_bytes(client, url))}
    except Exception as e:  # 네트워크·HTTP 오류는 항목별로 기록하고 계속 진행
        return {"id": model_id, "url": url, "error": _http.describe(e)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ids", nargs="+", help="조회할 정확한 모델 ID 목록")
    src.add_argument("--from-specs", help="variant-specs.json 경로. 명세에 쓰인 모델을 조회")
    ap.add_argument("--out", required=True, help="결과 JSON 저장 경로")
    ap.add_argument("--timeout", type=int, default=40)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)

    ids = a.ids if a.ids else ids_from_specs(a.from_specs)
    with _http.new_client(a.timeout) as client, concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(lambda m: fetch(client, m), ids))
    pathlib.Path(a.out).write_text(jsonio.dumps(results, indent=True), encoding="utf-8")

    ok = 0
    for r in results:
        if "error" in r:
            print(f"{r['id']}: ERROR {r['error']}")
            continue
        ok += 1
        eps = (r["response"].get("data") or {}).get("endpoints") or []
        print(f"{r['id']}: {len(eps)} endpoint(s)")
        for e in eps[:5]:
            print("  ", jsonio.dumps({k: e.get(k) for k in ("provider_name", "tag", "status", "context_length", "pricing")}))
    print(f"records={len(results)} successful={ok}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
