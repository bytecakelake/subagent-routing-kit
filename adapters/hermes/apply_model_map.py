#!/usr/bin/env python3
"""model-map-proposal.json 을 설치된 Hermes 의 delegation.backends.model_map 에 적용한다.

\b
python adapters/hermes/apply_model_map.py                 # 검증 + 적용 예정 요약 (아무것도 쓰지 않음)
python adapters/hermes/apply_model_map.py --print-yaml    # config.yaml 에 들어갈 블록 출력
python adapters/hermes/apply_model_map.py --apply         # 백업 → hermes config set → read-back 검증
python adapters/hermes/apply_model_map.py --apply --restart   # 위 작업 후 게이트웨이 재시작까지
python adapters/hermes/apply_model_map.py --apply -p biser    # 다른 프로필에 적용

`hermes` 실행 파일은 PATH, %LOCALAPPDATA%\\hermes\\bin\\hermes.exe, 또는 --hermes 순으로 찾는다.
설정 파일은 --config, HERMES_HOME, %LOCALAPPDATA%\\hermes, ~/.hermes 순으로 찾는다.
JSON 쓰기에 orjson 을 쓰며 추론 호출은 하지 않는다. 실제 설정 변경은 --apply 에서만 일어난다.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Annotated

import typer
from pydantic import FilePath, model_validator

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.hermes.export_model_map import problems  # noqa: E402
from core import cliutil, jsonio  # noqa: E402

PROPOSAL = ROOT / "adapters" / "hermes" / "model-map-proposal.json"
#: 설치된 advanced-delegation 플러그인의 검증 규칙(store.py::validate_route)과 model_map.py 가 읽는 키.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"})
TIERS = frozenset({"", "normal", "fast", "ultrafast"})
KEYS = frozenset({"name", "description", "provider", "model", "base_url", "api_key", "api_mode",
                  "reasoning_effort", "service_tier", "fallback_providers"})


def load(path=PROPOSAL):
    return jsonio.load_path(path)


def plugin_problems(options, default):
    """설치된 Hermes 가 조용히 건너뛰거나 거부할 옵션을 미리 잡는다."""
    errs = []
    names = [o.get("name") for o in options]
    for o in options:
        name = o.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            errs.append(f"{name!r}: 이름은 영숫자로 시작하고 영숫자·'.'·'_'·'-' 만, 64자 이하")
        extra = set(o) - KEYS
        if extra:
            errs.append(f"{name}: 알 수 없는 키 {sorted(extra)}")
        if not str(o.get("description") or "").strip():
            errs.append(f"{name}: 설명이 없으면 모델이 경로를 고를 수 없음")
        if not str(o.get("model") or "").strip():
            errs.append(f"{name}: model 없음")
        if not (str(o.get("provider") or "").strip() or str(o.get("base_url") or "").strip()):
            errs.append(f"{name}: provider 또는 base_url 이 필요함")
        effort = o.get("reasoning_effort")
        if effort not in (None, "") and effort not in EFFORTS:
            errs.append(f"{name}: 추론 강도 {effort!r} 는 Hermes 값이 아님({', '.join(sorted(EFFORTS))})")
        tier = o.get("service_tier")
        if tier is not None and tier not in TIERS:
            errs.append(f"{name}: 속도 단계 {tier!r} 는 normal/fast/ultrafast 중 하나여야 함")
        if "fallback_providers" in o and not isinstance(o["fallback_providers"], list):
            errs.append(f"{name}: fallback_providers 는 리스트여야 함")
    if default not in names:
        errs.append(f"기본 경로 {default!r} 가 옵션에 없음")
    return errs


def check(options, default):
    errs = plugin_problems(options, default) + problems(options, default)
    if errs:
        raise SystemExit("적용 중단 — 다음 문제를 먼저 고치십시오:\n  " + "\n  ".join(errs))


def yaml_block(options, default):
    lines = ["delegation:", "  backend: model_map", "  backends:", "    model_map:", "      options:"]
    for o in options:
        lines.append(f"        - name: {o['name']}")
        lines.append(f"          description: {jsonio.dumps(o['description'])}")
        for key in ("provider", "base_url", "model", "api_key", "api_mode",
                    "reasoning_effort", "service_tier"):
            if o.get(key):
                lines.append(f"          {key}: {jsonio.dumps(o[key])}")
        if "fallback_providers" in o:
            lines.append("          fallback_providers: []" if not o["fallback_providers"]
                         else f"          fallback_providers: {jsonio.dumps(o['fallback_providers'])}")
    lines.append(f"      default: {default}")
    return "\n".join(lines) + "\n"


def hermes_exe(explicit=None):
    for cand in (explicit, shutil.which("hermes"), shutil.which("hermes.exe")):
        if cand:
            return str(cand)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        p = pathlib.Path(local) / "hermes" / "bin" / "hermes.exe"
        if p.exists():
            return str(p)
    raise SystemExit("hermes 실행 파일을 찾지 못했습니다. --hermes 로 경로를 지정하십시오.")


def config_path(explicit=None):
    if explicit:
        return pathlib.Path(explicit)
    home = os.environ.get("HERMES_HOME")
    if home:
        return pathlib.Path(home) / "config.yaml"
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return pathlib.Path(local) / "hermes" / "config.yaml"
    return pathlib.Path.home() / ".hermes" / "config.yaml"


def run(exe, profile, args, timeout=180):
    argv = [exe] + (["-p", profile] if profile else []) + list(args)
    proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", shell=False, timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def read_back(exe, profile, cfg, options, default):
    """설정을 다시 읽어 17개 이름과 기본 경로가 실제로 들어갔는지 확인한다."""
    problems_found = []
    code, out = run(exe, profile, ["config", "get", "delegation.backend"])
    if code != 0 or "model_map" not in out:
        problems_found.append(f"delegation.backend 확인 실패 (exit {code}): {out.strip()[:200]}")
    code, out = run(exe, profile, ["config", "get", "delegation.backends.model_map"])
    text = out if code == 0 else ""
    if not text.strip():
        text = cfg.read_text(encoding="utf-8", errors="replace") if cfg.exists() else ""
    for o in options:
        if o["name"] not in text:
            problems_found.append(f"설정에서 {o['name']} 를 찾지 못함")
    if default not in text:
        problems_found.append(f"기본 경로 {default} 를 설정에서 찾지 못함")
    return problems_found


def restart_gateway(exe, profile, all_profiles=False):
    """게이트웨이를 재시작하고 상태를 다시 읽는다. 진행 중인 대화는 끊긴다."""
    argv = ["gateway", "restart", "-y"] + (["--all"] if all_profiles else [])
    code, out = run(exe, profile, argv, timeout=300)
    print(f"hermes {' '.join(argv)} -> exit {code}")
    if code != 0:
        print(out.strip()[:500])
        return code
    time.sleep(3)
    code2, status = run(exe, profile, ["gateway", "status"], timeout=90)
    print(status.strip()[:600])
    return code2


class Args(cliutil.Args):
    proposal: FilePath
    print_yaml: bool
    apply: bool
    restart: bool
    restart_all: bool
    yes: bool
    profile: str
    hermes: str
    config: str
    backup_dir: str

    @model_validator(mode="after")
    def _dependent_flags(self):
        if self.restart and not self.apply:
            raise ValueError("--restart 는 --apply 와 함께 쓰십시오 (적용 없이 재시작만 하지 않습니다).")
        if self.restart_all and not self.restart:
            raise ValueError("--restart-all 은 --restart 와 함께 쓰십시오 (재시작하지 않으면 효과가 없습니다).")
        return self


app = cliutil.make_app()


@app.command(help=__doc__)
def main(
    proposal: Annotated[pathlib.Path, typer.Option(help="model-map-proposal.json 경로", show_default="adapters/hermes/model-map-proposal.json")] = PROPOSAL,
    print_yaml: Annotated[bool, typer.Option("--print-yaml", help="config.yaml 에 들어갈 블록을 출력")] = False,
    apply: Annotated[bool, typer.Option("--apply", help="백업 후 hermes config set 으로 실제 적용")] = False,
    restart: Annotated[bool, typer.Option("--restart", help="적용 후 게이트웨이 재시작까지 수행")] = False,
    restart_all: Annotated[bool, typer.Option("--restart-all", help="재시작 시 모든 프로필의 게이트웨이를 종료")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="재시작 확인 질문을 건너뛴다")] = False,
    profile: Annotated[str, typer.Option("--profile", "-p", help="대상 Hermes 프로필(기본: 활성 프로필)")] = "",
    hermes: Annotated[str, typer.Option(help="hermes 실행 파일 경로")] = "",
    config: Annotated[str, typer.Option(help="백업·확인에 쓸 config.yaml 경로")] = "",
    backup_dir: Annotated[str, typer.Option(help="백업 파일을 둘 폴더(기본: config.yaml 과 같은 폴더)")] = "",
):
    a = cliutil.parse_args(Args, proposal=proposal, print_yaml=print_yaml, apply=apply, restart=restart,
                           restart_all=restart_all, yes=yes, profile=profile, hermes=hermes, config=config,
                           backup_dir=backup_dir)

    data = load(a.proposal)
    options, default = data["options"], data["default"]
    check(options, default)

    if a.print_yaml:
        sys.stdout.write(yaml_block(options, default))
        return

    models = {}
    for o in options:
        models[o["model"]] = models.get(o["model"], 0) + 1
    print(f"검증 통과: {len(options)}개 경로 / {len(models)}개 모델, 기본 경로 {default}")
    print("추론 강도:", ", ".join(f"{k}={v}" for k, v in sorted(
        {e: sum(1 for o in options if o.get('reasoning_effort') == e) for e in EFFORTS}.items()) if v))

    if not a.apply:
        print("\n아무것도 쓰지 않았습니다. 실제 적용은 --apply, 블록 확인은 --print-yaml.")
        return

    exe, cfg = hermes_exe(a.hermes), config_path(a.config)
    if not cfg.exists():
        raise SystemExit(f"config.yaml 을 찾지 못했습니다: {cfg}\n  --config 로 지정하십시오.")
    target_dir = pathlib.Path(a.backup_dir) if a.backup_dir else cfg.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    backup = target_dir / f"config.yaml.before-model-map-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(cfg, backup)
    print(f"백업: {backup}")

    payload = jsonio.dumps({"options": options, "default": default})
    for step in (["config", "set", "delegation.backends.model_map", payload],
                 ["config", "set", "delegation.backend", "model_map"]):
        code, out = run(exe, a.profile, step)
        if code != 0:
            raise SystemExit(f"실패: hermes {' '.join(step[:3])} (exit {code})\n{out.strip()[:500]}\n"
                             f"  백업으로 되돌리십시오: copy \"{backup}\" \"{cfg}\"")
    print("hermes config set 완료")

    bad = read_back(exe, a.profile, cfg, options, default)
    if bad:
        print("read-back 불일치:", *bad, sep="\n  ")
        print(f"  되돌리려면: copy \"{backup}\" \"{cfg}\"")
        raise typer.Exit(1)
    print(f"read-back 확인: {len(options)}개 경로와 기본 경로 {default} 모두 설정에 있음")
    if not a.restart:
        print("다음: hermes gateway restart -y   (또는 앱에서 재시작) → 새 세션에서 option 목록 확인")
        return

    if not a.yes:
        try:
            answer = input("게이트웨이를 지금 재시작할까요? 진행 중인 대화·cron·백그라운드 위임이 끊깁니다 [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes", "예"):
            print("재시작을 생략했습니다. 나중에: hermes gateway restart -y")
            return
    code = restart_gateway(exe, a.profile, a.restart_all)
    if code != 0:
        print("재시작 확인에 실패했습니다. `hermes gateway status` 로 직접 확인하십시오.")
        raise typer.Exit(1)
    print("재시작 완료. 새 세션에서 delegate_task 의 option 목록에 17개 이름이 보이는지 확인하십시오.")


if __name__ == "__main__":
    app()
