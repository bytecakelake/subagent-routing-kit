#!/usr/bin/env python3
"""Codex CLI 가 번들한 모델 카탈로그(`codex debug models --bundled`)에서 능력 스냅샷을 만든다.

네트워크·로그인이 필요 없다. 이 스냅샷은 "그 CLI 버전이 번들한 카탈로그"의 사본일 뿐이며, 계정별로
실제 노출되는 모델이나 서버가 나중에 바꾸는 값과 같다고 보장하지 않는다.

  python adapters/codex/collect_capabilities.py --catalog models.json --codex-version 0.169.0
  python adapters/codex/collect_capabilities.py --codex-bin /path/to/codex      # 직접 실행해 읽음
"""
import datetime
import json
import pathlib
import subprocess
import sys
from typing import Annotated, Optional

import typer

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import cliutil  # noqa: E402

OUT = ROOT / "adapters" / "codex" / "model-capabilities.json"
COMMAND = "codex debug models --bundled"


def build_snapshot(catalog: dict, *, codex_version: str, collected_at: str) -> dict:
    """카탈로그를 core/eligibility 가 읽는 형식으로 바꾼다. 카탈로그에 없는 값은 지어내지 않는다."""
    models, hidden = {}, []
    for m in catalog["models"]:
        slug = m["slug"]
        if m.get("visibility") != "list":
            hidden.append(slug)
            continue
        efforts = [lv["effort"] for lv in m.get("supported_reasoning_levels") or []]
        if not efforts:
            raise ValueError(f"{slug}: 카탈로그에 추론 강도 목록이 없다. 규칙을 적용할 수 없다")
        models[slug] = {
            "context_tokens": m["context_window"],
            "max_context_window": m.get("max_context_window"),
            "free": False,
            "input_modalities": sorted(m.get("input_modalities") or []),
            "long_context_surcharge_tokens": None,  # 카탈로그에 없음 -> 모름
            # 카탈로그가 광고하는 강도에 none 이 없으므로 끌 수 없는 것으로 다룬다(규칙은 none 을 거부).
            "reasoning_mandatory": True,
            "supported_efforts": efforts,
            "supports_reasoning": True,
            "supports_tools": True,  # 번들 카탈로그의 모든 항목이 shell 도구 유형을 가진다
            "multi_agent_version": m.get("multi_agent_version"),
        }
    return {
        "collected_at": collected_at,
        "source": {"codex_version": codex_version, "command": COMMAND,
                   "note": "CLI 번들 카탈로그의 사본. 계정별 노출·서버측 변경과 같다고 보장하지 않는다."},
        "excluded_hidden": sorted(hidden),
        "models": dict(sorted(models.items())),
    }


def _run(codex_bin, *args) -> str:
    return subprocess.run([str(codex_bin), *args], capture_output=True, text=True, check=True).stdout


app = cliutil.make_app()


@app.command(help=__doc__)
def main(
    catalog: Annotated[Optional[pathlib.Path], typer.Option("--catalog", help="debug models 출력 JSON 파일", exists=True)] = None,
    codex_bin: Annotated[Optional[pathlib.Path], typer.Option("--codex-bin", help="codex 실행 파일")] = None,
    codex_version: Annotated[Optional[str], typer.Option("--codex-version", help="카탈로그를 낸 CLI 버전")] = None,
    out: Annotated[pathlib.Path, typer.Option("--out", show_default="adapters/codex/model-capabilities.json")] = OUT,
):
    if bool(catalog) == bool(codex_bin):
        raise typer.BadParameter("--catalog 와 --codex-bin 중 정확히 하나를 준다")
    if codex_bin:
        data = json.loads(_run(codex_bin, "debug", "models", "--bundled"))
        codex_version = codex_version or _run(codex_bin, "--version").split()[-1]
    else:
        if not codex_version:
            raise typer.BadParameter("--catalog 를 쓸 때는 --codex-version 이 필요하다")
        data = json.loads(catalog.read_text(encoding="utf-8"))
    snap = build_snapshot(data, codex_version=codex_version, collected_at=datetime.date.today().isoformat())
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(snap['models'])} models, {len(snap['excluded_hidden'])} hidden excluded)")


if __name__ == "__main__":
    app()
