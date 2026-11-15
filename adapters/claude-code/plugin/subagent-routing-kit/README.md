# subagent-routing-kit (Claude Code plugin)

Ports the agent-neutral `core/eligibility` hard-rule judge and `core/policy` delegation policy to
Claude Code's `Agent`/`Task` subagent tool and plugin format. See
`docs/claude-codex-adapter-plan.md` (repo root) for the design record and official-doc citations.

## What it does

A `PreToolUse` hook (matcher `Agent|Task`) intercepts every subagent spawn and judges only what the
hook can actually observe:

- the call's `model` alias (per-call override), else the `model:` of a discovered agent file;
- an `effort` from the call (per-invocation parameter, Claude Code >= v2.1.292) or the agent file's
  `effort:` field.

These are checked against a Claude-Code-native capability snapshot (`capabilities.json`, a copy of
`adapters/claude-code/model-capabilities.json`, which carries sources and collection date). A
violation returns `permissionDecision: deny` with the reason and the discovered alternatives.

Agent files are discovered from `.claude/agents/**/*.md` in the working directory and every parent up
to the repository root (closest wins), plus `~/.claude/agents/`. A file Claude Code would skip (no
`name`/`description`, invalid name, unparseable YAML) is skipped here too.

## What it blocks

| Rule | Blocks when |
|---|---|
| Unknown model | The observable model (call override, else the agent file's `model:`) has no entry in `capabilities.json` |
| Effort not advertised | An observable `effort` is not in the model's `supported_efforts` (`low`, `medium`, `high`, `xhigh`, `max`) |
| Context / modality / tools | Only if the call carries such a need; an `Agent` call's `tool_input` carries none, so this is a no-op in practice |

## What it does NOT do (and cannot, from a hook)

- **No "agent is not registered" verdict.** Built-in agents (`Explore`, `Plan`, `general-purpose`,
  `statusline-setup`, `claude-code-guide`, `claude`), managed-settings agents, `--agents` CLI agents,
  plugin agents (`plugin:agent`) and `--add-dir` agents are not files this hook can scan. A name it
  cannot find is allowed, not blocked, and only an explicit per-call `model`/`effort` is judged.
- **No verdict on an omitted or `inherit` model.** The effective model depends on the session model,
  `CLAUDE_CODE_SUBAGENT_MODEL`, the provider, and `availableModels`; none reach the hook.
- **Aliases are provider-specific.** `opus`/`sonnet`/`haiku`/`fable` resolve to different models on
  Bedrock, Foundry, etc. (and `ANTHROPIC_DEFAULT_*_MODEL` can repoint them). The snapshot's alias rows
  describe the Anthropic API; the guard cannot see the provider, so they are an approximation.
- **A missing effort is not required.** The subagent then falls back to the session level
  (`/effort`, `--effort`), and `CLAUDE_CODE_EFFORT_LEVEL` overrides any declared effort. Neither is
  visible to the hook, so a declared effort is checked but a declared effort is not proof of the
  effective one.
- **Service tier / free-to-paid fallback.** Not Claude Code concepts; every route uses the one tier
  `core/eligibility` has verified (`normal`), so the check runs but never fires.
- **Input length and long-context surcharge.** `tool_input` carries no length information.
- **Hook failures fail open.** Malformed stdin or a guard exception allows the call. Needs `python3`
  on `PATH`; the `YAML` reader is a stdlib subset, not a full parser (duplicate keys etc. are not flagged).
- **Not a security boundary.** A parent can pick a different agent or omit the model.

## Install

The plugin directory is `adapters/claude-code/plugin/subagent-routing-kit` (the folder that contains
`.claude-plugin/plugin.json`), not its parent `plugin/`.

```bash
# Quick test, this session only (no marketplace needed):
claude --plugin-dir /path/to/subagent-routing-kit/adapters/claude-code/plugin/subagent-routing-kit

# Permanent: the marketplace root is adapters/claude-code (it holds .claude-plugin/marketplace.json)
claude plugin marketplace add /path/to/subagent-routing-kit/adapters/claude-code
claude plugin install subagent-routing-kit@subagent-routing-kit-local
```

Confirm the hook with `/hooks` inside a session.

## Verification status

- Offline unit tests: `python3 -m unittest tests.test_claude_code_routing_guard` (no Claude Code needed).
- Real CLI (`@anthropic-ai/claude-code` 2.1.325 via an isolated `npm exec`): `claude plugin validate`
  on the plugin directory and on the marketplace directory. That validator also reports an
  `ICON_MISSING` plugin-directory *warning*; it does not affect the result.
- **Not verified:** a live session where the hook actually denies a real `Agent` call (that needs an
  authenticated model session). Run one in your own environment before relying on it.

## Known limitations

- The capability snapshot is point-in-time (one model family, 2026-11-16). A full model ID or alias
  missing from it (for example an older `claude-opus-4-6`) is blocked in strict mode; set
  `ROUTING_GUARD_STRICT_UNKNOWN_MODEL=false` to warn instead, or refresh the snapshot.
- `~/.claude/agents` is read from `$HOME`/`%USERPROFILE%`; a relocated `CLAUDE_CONFIG_DIR` is not
  consulted.
