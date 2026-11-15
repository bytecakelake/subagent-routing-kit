# Codex 어댑터

`core/eligibility` 의 하드 규칙 일부를 Codex 의 `spawn_agent` 호출 앞(PreToolUse 훅)에서 돌리고, `core/policy` 를 Codex 스킬로 싣는 플러그인입니다. 기준 CLI 는 `@openai/codex@0.169.0` 입니다.

## 구성

```text
adapters/codex/
  collect_capabilities.py     codex debug models --bundled 출력 -> model-capabilities.json
  model-capabilities.json     능력 스냅샷(CLI 0.169.0 번들 카탈로그의 list 노출 9개 모델)
  sync_plugin.py              core 판정기·정책·스냅샷을 플러그인 폴더로 복사 (--check 로 일치 검사)
  marketplace/                로컬 마켓플레이스 루트 (codex plugin marketplace add 대상)
    .agents/plugins/marketplace.json
    plugins/subagent-routing-kit/
      .codex-plugin/plugin.json
      hooks/hooks.json        최상위 "hooks" 래퍼 안의 PreToolUse, matcher "spawn_agent|Agent"
      scripts/                guard_hook.py(진입점) guard.py(로직) eligibility_rules.py(core 사본) capabilities.json(스냅샷 사본)
      skills/subagent-orchestration/   SKILL.md(손으로 작성) + core/policy 사본
```

## 설치 (로컬 마켓플레이스)

```bash
codex plugin marketplace add ./adapters/codex/marketplace     # 경로는 ./ 로 시작해야 로컬 경로로 인식됨
codex plugin add subagent-routing-kit@subagent-routing-kit
```

설치만으로는 훅이 실행되지 않습니다. 플러그인 훅은 관리되지 않는 훅이라 **사용자가 `/hooks`(데스크톱은 Review hooks)에서 검토하고 신뢰해야** 돌고, 플러그인 업데이트로 스크립트가 바뀌면 다시 검토해야 합니다. 훅은 `python3` 이 PATH 에 있고 3.11 이상(`tomllib`)일 때만 동작합니다.

## 무엇을 검사하나

호출 인자(`model`, `reasoning_effort`, `agent_type`, `items`)와 프로젝트(`.codex/agents/*.toml`, cwd 에서 git 루트까지)·사용자(`$CODEX_HOME/agents`) custom agent 파일만 봅니다.

| 결과 | 조건 |
|---|---|
| 차단 | 후보 설정(호출 값, 일치하는 custom agent 의 값) 중 하나라도 스냅샷에 없는 모델, 그 모델이 광고하지 않는 강도, `none`, 이미지 입력인데 이미지 비지원 모델 |
| **자격 불명** | `model` 또는 `reasoning_effort` 가 호출과 읽을 수 있는 custom agent 어디에도 없음, `agent_type` 이 읽을 수 없는 역할(내장 역할·`config.toml` 역할) |
| 통과 | 모든 후보가 규칙을 통과하고 모델·강도가 모두 확인됨 |

- 자격 불명은 기본이 **차단**(fail-closed)입니다. 환경변수 `SUBAGENT_ROUTING_UNKNOWN=allow` 로 통과시킬 수 있고, 다른 값은 차단으로 해석합니다.
- **통과는 "요청한 설정이 스냅샷에 있다"는 뜻이지 서브에이전트가 최종으로 쓰는 모델을 확정한 것이 아닙니다.** 호출 인자를 생략하면 부모·`[agents]` 기본값(`default_subagent_model` 등)·역할이 정하고, custom agent 가 호출 인자를 나중에 덮어쓸 수 있습니다. 어느 쪽이 이기는지 이 훅은 모르므로 두 값을 모두 검사합니다. `config.toml` 은 읽지 않습니다.
- `spawn_agent` V1(`message`/`items`, `fork_context`)과 V2(`task_name`+`message`, `fork_turns`)는 필드가 다르고, `model`/`reasoning_effort` 가 스키마에서 숨겨질 수 있습니다. 숨겨지면 호출 인자로는 지정할 수 없으므로 custom agent 로 지정해야 합니다.
- V2 에서 훅이 보는 도구 이름이 `collaborationspawn_agent` 로 붙어 올 수 있다는 보고가 있어([openai/codex#57539](https://github.com/openai/codex/issues/57539)) matcher 를 `spawn_agent|Agent`(미고정 정규식)로 두었습니다. 이 CLI 버전에서 그 이름이 실제로 어떻게 보이는지는 모델 호출이 필요해 확인하지 못했습니다.
- 훅이 죽거나 시간 초과·종료 코드 1 이면 Codex 는 호출을 막지 않습니다(fail-open). 보안 경계가 아닙니다.

## 기존 core/eligibility 재사용 범위

`core/` 는 한 줄도 바꾸지 않았고 `eligibility_rules.py` 는 `core/eligibility/rules.py` 의 바이트 단위 사본입니다.

- **실제로 도는 규칙**: `unknown_model`, `effort_unadvertised`, `effort_cannot_disable`, `modality_unsupported`.
- **돌지만 무력화한 규칙**: `service_tier_*`(`spawn_agent` 에 service_tier 인자가 없어 `normal` 로 고정), `route_not_registered`(후보 하나를 스스로 등록).
- **적용 못 하는 규칙**: `effort_implicit`(생략은 위의 "자격 불명"으로 별도 처리), `context_exceeded`·`long_context_surcharge`(입력 토큰 수가 훅 입력에 없음, 카탈로그에도 할증 수치 없음), `tools_unsupported`(작업별 도구 요구 정보 없음), `free_to_paid_fallback`(Codex 에 그 개념 없음), 쓰기 범위·승인 필요 여부(훅 입력에 없음).
- 이 어댑터가 core 수정 없이 붙었다는 것은 중립성의 증거 하나일 뿐이며, `docs/architecture.md` 의 완료 정의가 끝나기 전에는 "범용"이라고 쓰지 않습니다.

## 능력 스냅샷

`model-capabilities.json` 은 `codex debug models --bundled`(로그인·네트워크 불필요)의 사본이며 CLI 버전과 명령이 `source` 에 있습니다. 계정별 노출 모델이나 서버 측 변경과 같다고 보장하지 않습니다. `list` 로 노출되지 않는 3개는 `excluded_hidden` 으로 빼서 `unknown_model` 이 됩니다. 값 중 카탈로그가 말하지 않는 것은 지어내지 않았습니다: `long_context_surcharge_tokens` 는 `null`(모름), `reasoning_mandatory` 는 카탈로그가 `none` 강도를 광고하지 않아 `true` 로 두었습니다(= `none` 거부, 파생값). `context_tokens` 는 `context_window`(예: 272000)이고 `max_context_window`(예: 872000)는 참고로만 둡니다. 갱신:

```bash
python adapters/codex/collect_capabilities.py --codex-bin <codex 경로>   # 또는 --catalog models.json --codex-version X
python adapters/codex/sync_plugin.py
```

이전 계획 문서(`docs/claude-codex-adapter-plan.md`)의 `gpt-5.1-codex-max` 1개 모델 가정은 이 번들 카탈로그에 없어 폐기했습니다.

## 검증 수준

| 수준 | 내용 | 상태 |
|---|---|---|
| 단위 | `tests/test_codex_routing_guard.py` 훅 로직(후보·불명·role 탐색·V1/V2 모양) | 통과 |
| 서브프로세스 | 같은 파일의 진입점 테스트: stdin JSON -> stdout deny JSON·종료 코드 | 통과 |
| 패키지 | `tests/test_codex_plugin_package.py`: 매니페스트·`hooks` 래퍼·matcher·마켓플레이스·동기화·표준 라이브러리 경계 | 통과 |
| 실제 CLI 설치 | `CODEX_BIN=<codex 경로>` 로 같은 파일의 선택 검사: 격리 HOME/CODEX_HOME 에서 `marketplace add`, `plugin add`, 캐시 파일, app-server `hooks/list` 로 훅 발견(`source=plugin`, `trustStatus=untrusted`, `${PLUGIN_ROOT}` 전개), 전개된 명령 직접 실행 | 0.169.0 에서 통과 |
| **실제 훅 발동** | 신뢰 승인 후 모델이 `spawn_agent` 를 호출할 때 훅이 실제로 막는지 | **미검증** (모델 호출·인증 필요, 사용하지 않음) |
| Windows | `commandWindows` 없이 `python3 "${PLUGIN_ROOT}/..."` 만 둠. Windows 셸에서의 실행 | **미검증** |

훅 발동 전까지 "Codex 에서 강제된다"고 주장하지 않습니다.
