#!/usr/bin/env python3
"""core/policy 의 정책 문서를 Hermes 스킬 폴더로 복사한다. 표준 라이브러리만 사용.

스킬은 설치되는 사본이라 저장소 밖에서 core/policy 를 읽을 수 없다. 이 스크립트가 사본을 만들고,
--check 는 사본이 원본과 다르면 비정상 종료한다(파일은 건드리지 않는다).
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILL = ROOT / "adapters" / "hermes" / "skill" / "subagent-orchestration"
MAPPING = {
    ROOT / "core" / "policy" / "orchestration-policy.md": SKILL / "references" / "orchestration-policy.md",
    ROOT / "core" / "policy" / "routing-policy.md": SKILL / "references" / "routing-policy.md",
    ROOT / "core" / "policy" / "task-contract.md": SKILL / "templates" / "task-contract.md",
    ROOT / "core" / "spec" / "output-contract.schema.json": SKILL / "templates" / "output-contract.schema.json",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="복사하지 않고 일치 여부만 검사")
    a = ap.parse_args(argv)
    drift = []
    for src, dst in MAPPING.items():
        want = src.read_bytes()
        have = dst.read_bytes() if dst.exists() else None
        if have == want:
            continue
        drift.append(dst.relative_to(ROOT).as_posix())
        if not a.check:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(want)
    if a.check:
        if drift:
            print("DRIFT:", *drift, sep="\n  ")
            return 1
        print("OK: 스킬 사본이 core/policy 와 일치")
        return 0
    print("updated:" if drift else "already in sync", *drift, sep="\n  " if drift else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
