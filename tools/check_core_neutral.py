#!/usr/bin/env python3
"""core/ 가 특정 에이전트 프레임워크에 묶이지 않았는지 검사한다. 표준 라이브러리만 사용.

core/ 아래 텍스트 파일에서 금지 용어가 나오면 비정상 종료한다.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"hermes|delegate_task|model_map|advanced-delegation|/hermes-home|/workspace/", re.I)
TEXT_SUFFIXES = {".md", ".json", ".py", ".txt", ".yaml", ".yml", ".toml"}


def main(core=None):
    core = pathlib.Path(core) if core else ROOT / "core"
    hits = []
    for p in sorted(core.rglob("*")):
        if not p.is_file() or p.suffix not in TEXT_SUFFIXES:
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            m = FORBIDDEN.search(line)
            if m:
                hits.append(f"{p.relative_to(core.parent).as_posix()}:{n}: {m.group(0)}")
    if hits:
        print("core/ 에 에이전트 종속 용어가 있습니다:", *hits, sep="\n  ")
        return 1
    print("OK: core/ 에 에이전트 종속 용어 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
