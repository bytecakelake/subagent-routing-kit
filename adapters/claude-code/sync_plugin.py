#!/usr/bin/env python3
"""Copy core/eligibility, the native capability snapshot, and core/policy into the
Claude Code plugin folder.

The plugin is an installed copy that Claude Code loads without this repo's
dependencies, so it cannot import core/ directly. This script makes the copy;
--check fails (without touching files) when a copy has drifted from its source.

  python adapters/claude-code/sync_plugin.py          # copy
  python adapters/claude-code/sync_plugin.py --check  # check only
"""
import pathlib
import sys
from typing import Annotated

import typer

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import cliutil  # noqa: E402

PLUGIN = ROOT / "adapters" / "claude-code" / "plugin" / "subagent-routing-kit"
SKILL = PLUGIN / "skills" / "subagent-orchestration"
MAPPING = {
    ROOT / "core" / "eligibility" / "rules.py": PLUGIN / "eligibility_rules.py",
    ROOT / "adapters" / "claude-code" / "model-capabilities.json": PLUGIN / "capabilities.json",
    ROOT / "core" / "policy" / "orchestration-policy.md": SKILL / "references" / "orchestration-policy.md",
    ROOT / "core" / "policy" / "routing-policy.md": SKILL / "references" / "routing-policy.md",
    ROOT / "core" / "policy" / "task-contract.md": SKILL / "templates" / "task-contract.md",
    ROOT / "core" / "spec" / "output-contract.schema.json": SKILL / "templates" / "output-contract.schema.json",
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
