#!/usr/bin/env python3
"""core 의 판정기와 능력 데이터를 routing-guard 플러그인 폴더로 복사한다.

플러그인은 설치되는 사본이라 저장소 밖에서 core/ 를 읽을 수 없다. 이 스크립트가 사본을 만들고,
--check 는 사본이 원본과 다르면 비정상 종료한다(파일은 건드리지 않는다).

  python adapters/hermes/sync_plugin.py          # 복사
  python adapters/hermes/sync_plugin.py --check  # 일치 여부만 검사
"""
import pathlib
import sys
from typing import Annotated

import typer

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # 스크립트로 직접 실행해도 core 를 import 할 수 있게 한다

from core import cliutil  # noqa: E402

PLUGIN = ROOT / "adapters" / "hermes" / "plugin" / "routing-guard"
MAPPING = {
    ROOT / "core" / "eligibility" / "rules.py": PLUGIN / "eligibility_rules.py",
    ROOT / "core" / "spec" / "model-capabilities.json": PLUGIN / "capabilities.json",
}


app = cliutil.make_app()


@app.command(help=__doc__)
def main(
    check: Annotated[bool, typer.Option("--check", help="복사하지 않고 일치 여부만 검사")] = False,
):
    drift = []
    for src, dst in MAPPING.items():
        want = src.read_bytes()
        have = dst.read_bytes() if dst.exists() else None
        if have == want:
            continue
        drift.append(dst.relative_to(ROOT).as_posix())
        if not check:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(want)
    if check:
        if drift:
            print("DRIFT:", *drift, sep="\n  ")
            raise typer.Exit(1)
        print("OK: 플러그인 사본이 core 와 일치")
        return
    print("updated:" if drift else "already in sync", *drift, sep="\n  " if drift else "")


if __name__ == "__main__":
    app()
