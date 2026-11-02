#!/usr/bin/env python3
"""OpenRouter 모델 목록에서 하드 규칙 판정에 필요한 모델별 능력만 추려 JSON으로 저장한다.

판정기(core/eligibility)는 이 파일만 읽는다. 공개 API만 사용하며 인증 키가 필요 없다.
orjson 과 httpx 를 사용한다(requirements.txt).

예:
  python core/catalog/build_capabilities.py --specs core/spec/variant-specs.json --out core/spec/model-capabilities.json
  python core/catalog/build_capabilities.py --models-json models.json --specs ... --out ...
"""
import argparse
import datetime
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # 스크립트로 직접 실행해도 core 를 import 할 수 있게 한다

from core import jsonio  # noqa: E402
from core.catalog import _http  # noqa: E402

MODELS_URL = "https://openrouter.ai/api/v1/models"
SCHEMA = 1


def extract_caps(m):
    """모델 한 건의 API 응답을 판정용 능력 사전으로 변환한다."""
    params = m.get("supported_parameters") or []
    reasoning = m.get("reasoning") or {}
    efforts = reasoning.get("supported_efforts")
    pricing = m.get("pricing") or {}
    thresholds = [o["min_prompt_tokens"] for o in (pricing.get("overrides") or []) if "min_prompt_tokens" in o]
    return {
        "context_tokens": m.get("context_length"),
        "input_modalities": sorted((m.get("architecture") or {}).get("input_modalities") or []),
        "supports_tools": "tools" in params,
        "supports_reasoning": "reasoning" in params,
        "reasoning_mandatory": bool(reasoning.get("mandatory")),
        # None 은 "강도 선택 목록이 공개되지 않음"을 뜻한다. 빈 목록과 구분한다.
        "supported_efforts": list(efforts) if isinstance(efforts, list) else None,
        "long_context_surcharge_tokens": min(thresholds) if thresholds else None,
        "free": str(pricing.get("prompt")) == "0" and str(pricing.get("completion")) == "0",
    }


def models_in_specs(path):
    specs = jsonio.load_path(path)
    out = []
    for s in specs:
        if s["model"] not in out:
            out.append(s["model"])
    return out


def load_models(models_json, timeout):
    if models_json:
        raw = pathlib.Path(models_json).read_bytes()
        source = {"file": pathlib.Path(models_json).name, "sha256": hashlib.sha256(raw).hexdigest()}
    else:
        with _http.new_client(timeout) as client:
            raw = _http.get_bytes(client, MODELS_URL)
        source = {"url": MODELS_URL}
    data = jsonio.loads(raw)["data"]
    return {m["id"]: m for m in data}, source


def build(models, wanted):
    missing = [w for w in wanted if w not in models]
    if missing:
        raise SystemExit("모델 목록에 없는 모델: " + ", ".join(missing))
    return {w: extract_caps(models[w]) for w in sorted(wanted)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--specs", required=True, help="variant-specs.json 경로. 명세에 쓰인 모델만 수집")
    ap.add_argument("--out", required=True)
    ap.add_argument("--models-json", help="미리 받은 모델 목록(OpenRouter /models 응답). 없으면 공개 API에서 받는다")
    ap.add_argument("--collected-at", default=datetime.date.today().isoformat())
    ap.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args(argv)

    models, source = load_models(a.models_json, a.timeout)
    caps = build(models, models_in_specs(a.specs))
    doc = {"schema": SCHEMA, "collected_at": a.collected_at, "source": source, "models": caps}
    pathlib.Path(a.out).write_text(jsonio.dumps(doc, indent=True, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {a.out}: {len(caps)} models, collected_at={a.collected_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
