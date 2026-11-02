#!/usr/bin/env python3
"""OpenRouter 모델 목록에서 하드 규칙 판정에 필요한 모델별 능력만 추려 JSON으로 저장한다.

판정기(core/eligibility)는 이 파일만 읽는다. 공개 API만 사용하며 인증 키가 필요 없다.
orjson 과 httpx 를 사용한다(requirements.txt).

예:

\b
python core/catalog/build_capabilities.py --specs core/spec/variant-specs.json --out core/spec/model-capabilities.json
python core/catalog/build_capabilities.py --models-json models.json --specs ... --out ...
"""
import datetime
import hashlib
import pathlib
import sys
from typing import Annotated, Optional

import typer
from pydantic import FilePath, Field

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # 스크립트로 직접 실행해도 core 를 import 할 수 있게 한다

from core import cliutil, jsonio  # noqa: E402
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


class Args(cliutil.Args):
    specs: FilePath
    out: pathlib.Path
    models_json: Optional[FilePath] = None
    collected_at: datetime.date
    timeout: int = Field(gt=0)


app = cliutil.make_app()


@app.command(help=__doc__)
def main(
    specs: Annotated[pathlib.Path, typer.Option(help="variant-specs.json 경로. 명세에 쓰인 모델만 수집")],
    out: Annotated[pathlib.Path, typer.Option(help="결과 JSON 저장 경로")],
    models_json: Annotated[Optional[pathlib.Path], typer.Option(help="미리 받은 모델 목록(OpenRouter /models 응답). 없으면 공개 API에서 받는다")] = None,
    collected_at: Annotated[Optional[str], typer.Option(help="수집일 YYYY-MM-DD. 기본: 오늘")] = None,
    timeout: Annotated[int, typer.Option(help="요청 제한 시간(초)")] = 60,
):
    a = cliutil.parse_args(Args, specs=specs, out=out, models_json=models_json,
                           collected_at=collected_at or datetime.date.today().isoformat(), timeout=timeout)
    models, source = load_models(a.models_json, a.timeout)
    caps = build(models, models_in_specs(a.specs))
    doc = {"schema": SCHEMA, "collected_at": a.collected_at.isoformat(), "source": source, "models": caps}
    a.out.write_text(jsonio.dumps(doc, indent=True, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {a.out}: {len(caps)} models, collected_at={a.collected_at.isoformat()}")


if __name__ == "__main__":
    app()
