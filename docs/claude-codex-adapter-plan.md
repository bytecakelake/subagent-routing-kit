# 계획: Claude Code / Codex 플러그인 어댑터 (두 번째·세 번째 어댑터)

`docs/architecture.md`의 "이전 작업 순서 5" (두 번째 어댑터 후보를 하나 골라 형식을 확인하고, 중립성이
실제로 성립하는지 검증한다)를 Claude Code와 Codex 두 타겟에 대해 수행한다. 스코프는 **전체 포팅**으로
확정했다(2026-11-16, 사용자 결정): 두 CLI의 네이티브 모델별 능력 스냅샷을 새로 조사·작성해서
`core/eligibility` 규칙 전체를 포팅한다. PR은 타겟당 1개, 총 2개(`adapters/claude-code/`,
`adapters/codex/`). 각 PR 안에 그 타겟의 능력 스냅샷 수집 커밋과 플러그인 구현 커밋을 함께 둔다.

## 공식 문서로 확인한 사실 (2026-11-16 조사)

### 플러그인 포맷 (둘 다 공식 문서로 확인됨)

- **Claude Code**: 매니페스트 `.claude-plugin/plugin.json` (선택, 없으면 표준 레이아웃 스캔).
  구성요소: `skills/`, `agents/`, `hooks/hooks.json`, `.mcp.json` 등. 마켓플레이스는
  `.claude-plugin/marketplace.json`. 세션 전용 테스트는 `--plugin-dir <path>`.
- **Codex**: 매니페스트 `.codex-plugin/plugin.json`. 마켓플레이스는 `.agents/plugins/marketplace.json`
  (레거시 `.claude-plugin/marketplace.json` 위치도 인식). 훅은 플러그인이 활성화되면 자동 로드되지만
  **신뢰 확인 전에는 실행되지 않는다** — `/hooks`에서 사용자가 직접 승인해야 함(관리자 배포 훅 제외).
- **훅 스키마는 두 CLI가 실질적으로 동일하다**: `hooks/hooks.json`에 이벤트(`PreToolUse` 등) → matcher
  배열 → `{"type": "command", "command": "...", "timeout": N}`. stdin으로 JSON
  (`hook_event_name`, `tool_name`, `tool_input`)을 받고, 차단은 exit code 2 + stderr 또는
  exit 0 + stdout JSON `{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "permissionDecision": "deny", "permissionDecisionReason": "..."}}`.
  Codex는 Claude 호환을 위해 `PLUGIN_ROOT`/`PLUGIN_DATA`와 함께
  `CLAUDE_PLUGIN_ROOT`/`CLAUDE_PLUGIN_DATA`도 환경변수로 넘긴다.
- **서브에이전트 스폰 도구 이름이 두 CLI에서 `Agent`로 일치한다.** Claude Code는 `Task` 도구를
  v2.1.63에서 `Agent`로 이름을 바꾸고 `Task(...)`를 별칭으로 유지. Codex는 로컬 함수 도구
  `spawn_agent`가 매처 별칭 `Agent`에도 걸린다. 따라서 두 훅 모두 `matcher: "Agent"`로 설치한다.
- **Skills(`SKILL.md`)는 세 환경(Hermes/Claude Code/Codex) 모두 동일 포맷으로 읽는다.** 이식 위험이
  가장 낮은 구성요소.

### 네이티브 서브에이전트 설정의 축 차이 (중요한 비대칭)

| 축 | Claude Code `.claude/agents/*.md` frontmatter | Codex `.codex/agents/*.toml` |
|---|---|---|
| 모델 | `model:` (별칭 opus/sonnet/haiku/fable 또는 전체 ID) | `model` |
| 추론 강도 | **필드 없음** (강도는 세션 전역 `/effort`·`--effort`로만 설정, 에이전트별 고정 불가) | `model_reasoning_effort` (에이전트별 고정 가능) |
| 서비스 티어 | 개념 없음 | 개념 없음 |
| 무료→유료 폴백 | 개념 없음 (구독/API 과금, OpenRouter류 무료 모델 없음) | 개념 없음 |

**결론**: Codex는 `core/eligibility`의 추론강도 규칙(`effort_implicit`/`effort_unadvertised`/
`effort_cannot_disable`)까지 의미 있게 적용된다. Claude Code는 네이티브 포맷에 그 축 자체가 없으므로
해당 규칙은 **구조적으로 항상 통과**시키고(막아도 사용자가 고칠 방법이 없음), README에 공식 문서
인용과 함께 "미지원 아님, 플랫폼에 그 축이 없음"으로 명시한다. 서비스 티어·무료 폴백 축은 둘 다
없으므로 모든 네이티브 경로의 `service_tier`를 `"normal"`로 고정해 해당 규칙을 무해화한다(검사는
돌지만 항상 통과). 모달리티·도구·컨텍스트초과 규칙은 `delegate_task`와 마찬가지로 `tool_input`에
입력 길이 정보가 없어 길이 기반 규칙은 경고 없이 건너뛴다(Hermes routing-guard와 동일한 한계).

### 네이티브 모델 능력 스냅샷 (수집, 출처 명시)

**Claude Code** (출처: code.claude.com/docs/en/model-config, platform.claude.com/docs/en/models/overview,
platform.claude.com/docs/en/build-with-claude/effort — 2026-11-16 조회):

| 별칭/ID | context_tokens | supported_efforts | reasoning_mandatory |
|---|---|---|---|
| opus / claude-opus-5-5 | 1,000,000 | low,medium,high,xhigh,max | true (always adaptive) |
| sonnet / claude-sonnet-5-5 | 1,000,000 | low,medium,high,xhigh,max | true |
| haiku / claude-haiku-5-5 | 1,000,000 | low,medium,high,xhigh,max | true |
| fable / claude-fable-5-2 | 1,000,000 | low,medium,high,xhigh,max | true |

`long_context_surcharge_tokens`는 이번 조사에서 공식 수치를 확인하지 못해 `null`(모름)로 둔다 —
core 규칙은 모름을 경고로만 처리하므로 안전하다. `input_modalities={text,image}`,
`supports_tools=true`, `free=false` 전부 공식 문서로 확인.

**Codex** (출처: github.com/openai/codex docs/config.md, developers.openai.com model 페이지,
openai.com/index/gpt-5-1-codex-max — 2026-11-16 조회):

| 모델 | context_tokens | supported_efforts |
|---|---|---|
| gpt-5.1-codex-max | 400,000 | minimal,low,medium,high,xhigh |

범위는 1개 모델로 제한(다른 Codex 모델의 정확한 컨텍스트/강도 조합을 이번 조사에서 확인하지 못함).
목록에 없는 모델은 `unknown_model`로 거부되는 것이 의도된 동작이며, 새 모델을 쓰려면 스냅샷을 먼저
갱신해야 한다(Hermes routing-guard의 `capabilities_path` 갱신과 동일한 운영 부담).

## 설계

각 어댑터는 `adapters/hermes/`와 동일한 3단 구조를 따른다: 원본 데이터(스냅샷) → 동기화 스크립트 →
설치되는 플러그인 사본. 차이: 경로 레지스트리를 Hermes처럼 "앱 설정에서 읽기"가 아니라 **프로젝트의
네이티브 에이전트 정의 파일을 훅 실행 시점에 직접 스캔**해서 만든다(`.claude/agents/*.md` +
`~/.claude/agents/*.md`, 또는 `.codex/agents/*.toml` + `~/.codex/agents/*.toml`). 이것이
Hermes의 "현재 등록된 model_map"과 대응되는, 각 플랫폼에서 실제로 존재하는 단일 진실 소스다.

```text
adapters/claude-code/
  model-capabilities.json       # 네이티브 스냅샷 원본 (수집일·출처 포함)
  sync_plugin.py                # core/eligibility/rules.py + 스냅샷 + 스킬을 플러그인 사본으로 복사
  plugin/subagent-routing-kit/
    .claude-plugin/plugin.json
    hooks/hooks.json            # PreToolUse, matcher "Agent"
    guard_hook.py                # 훅 진입점 (stdin JSON 읽기 → 종료코드/JSON 출력)
    guard.py                     # 순수 로직 (에이전트 파일 스캔 → Route 목록 → core 판정)
    agent_frontmatter.py         # 최소 YAML frontmatter 파서 (표준 라이브러리만, 스칼라 key: value 한정)
    eligibility_rules.py         # core/eligibility/rules.py 사본
    capabilities.json            # model-capabilities.json 사본
    skills/subagent-orchestration/SKILL.md
    README.md
  README.md
adapters/codex/
  (동일 구조, .codex-plugin/plugin.json, agent_toml.py 는 표준 tomllib 사용)
```

## 지원하지 못하는 항목 (README에 명시할 목록)

- Claude Code: 추론강도 규칙 전부(네이티브 축 없음), 장문 할증(수치 미확인), 입력 토큰 길이 기반 규칙
  (`tool_input`에 길이 정보 없음), 모달리티/도구 요구사항(작업별 요구사항이 훅 인자에 없음).
- Codex: 장문 할증(공식 수치 미확인), 입력 토큰 길이 기반 규칙, 모달리티/도구 요구사항(동일 이유).
  프로젝트 디렉터리 탐지는 CWD 기준으로 가정(공식 "현재 프로젝트 경로" 환경변수를 확인하지 못함) —
  실제 Codex 설치로 검증되지 않음.
- 두 어댑터 모두: `claude`/`codex` CLI 바이너리가 이 샌드박스에 없어(글로벌 npm 설치가 승인 정책으로
  차단됨) **실제 설치·훅 발동으로 검증하지 못했다.** 순수 로직 단위 테스트만 통과 확인. 사용자의 실제
  환경에서 `claude plugin validate` / `codex plugin validate`(또는 `--plugin-dir` 세션 테스트)로
  최종 확인이 필요하다 — `apply_model_map.py --apply`의 기존 선례와 동일한 한계.

## 작업 순서

1. [x] 공식 문서 조사 및 스코프 확정(이 문서).
2. [ ] PR 1 (`feature/claude-code-plugin-adapter`): `adapters/claude-code/` 전체 구현 + 단위 테스트 +
   README + `tools/check_core_neutral.py` 대상 확장 + 루트 README/architecture.md 갱신.
3. [ ] PR 2 (`feature/codex-plugin-adapter`): `adapters/codex/` 전체 구현(동일 패턴, TOML 파서).
4. [ ] 두 PR 모두 사용자 환경에서 `claude plugin validate` / `codex plugin validate` 실행 결과를
   받아 이 문서의 "지원하지 못하는 항목"을 갱신(검증 완료 항목 승격).

## 진행 기록

- 2026-11-16: 범위를 전체 포팅으로 확정. 공식 문서 조사 완료(플러그인 포맷, 훅 스키마, 서브에이전트
  스폰 도구 이름, 네이티브 설정 축 차이, 모델 능력 스냅샷). PR 1 착수.
- 2026-11-16 (Codex 구현 정정): 위 조사 중 다음은 구현 과정에서 실제 CLI(`@openai/codex@0.169.0`)와 공식 문서로 바로잡았다.
  (1) 모델 스냅샷은 `gpt-5.1-codex-max` 1개가 아니라 `codex debug models --bundled` 의 노출 9개 모델이다(`adapters/codex/model-capabilities.json`).
  (2) 이 샌드박스에서도 `npm exec @openai/codex@0.169.0` 로 CLI 를 받아 마켓플레이스 add·plugin add·훅 발견을 실제로 수행했다("바이너리 없음" 한계 해소). 훅 발동은 모델 호출이 필요해 여전히 미검증.
  (3) 훅 설정은 최상위 `hooks` 래퍼가 필요하고, 설치된 비관리 훅은 `/hooks` 신뢰 전에는 실행되지 않는다.
  (4) `spawn_agent` 는 V1(`fork_context`)/V2(`task_name`, `fork_turns`)의 필드가 다르고 `model`/`reasoning_effort` 가 숨겨질 수 있으며, custom agent 가 모델을 나중에 덮어쓸 수 있어 최종 모델은 확정하지 않는다. V2 의 훅 도구 이름이 `collaborationspawn_agent` 로 보고되는 이슈가 있어 matcher 는 `spawn_agent|Agent`.
  (5) 프로젝트 탐지는 훅 입력의 `cwd` 를 쓴다.
