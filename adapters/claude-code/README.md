# adapters/claude-code

Second adapter (after Hermes). Converts the agent-neutral `core/eligibility` judge and
`core/policy` delegation policy into a Claude Code plugin. Design record, official-doc citations,
and scope decisions: `docs/claude-codex-adapter-plan.md` (repo root).

```text
adapters/claude-code/
  model-capabilities.json   원본 네이티브 모델 능력 스냅샷 (Hermes 의 core/spec/model-capabilities.json
                             에 대응하지만 Claude 모델 별칭/ID 기준. 수집일·출처 포함)
  .claude-plugin/marketplace.json  로컬 마켓플레이스 (루트 = 이 디렉터리, source ./plugin/subagent-routing-kit)
  sync_plugin.py             core/eligibility, 스냅샷, core/policy 를 plugin/ 사본으로 복사
  plugin/subagent-routing-kit/
    .claude-plugin/plugin.json
    hooks/hooks.json         {"hooks": {"PreToolUse": ...}} (wrapper required), matcher "Agent|Task"
    guard_hook.py             훅 진입점 (stdin JSON -> stdout 판정 JSON)
    guard.py                  순수 판정 로직 (관측 가능한 model/effort 만 core 판정에 전달)
    agent_frontmatter.py      YAML frontmatter 부분집합 파서 + 파싱 불가 파일 건너뛰기 (표준 라이브러리만)
    eligibility_rules.py      core/eligibility/rules.py 사본 (sync_plugin.py 로 동기화)
    capabilities.json         model-capabilities.json 사본
    skills/subagent-orchestration/SKILL.md
    README.md                 플러그인 설치·범위·한계
```

## 사용

```bash
# 사본 동기화 (core/ 또는 model-capabilities.json 을 고치면 실행)
python adapters/claude-code/sync_plugin.py
python adapters/claude-code/sync_plugin.py --check   # 일치 여부만 검사

# 단위 테스트 (plain python3 로 통과해야 함 — 플러그인은 표준 라이브러리만 사용)
python3 -m unittest tests.test_claude_code_routing_guard
```

설치·훅 동작 범위는 `plugin/subagent-routing-kit/README.md`를 보십시오.
