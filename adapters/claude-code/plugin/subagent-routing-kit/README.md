# subagent-routing-kit (Claude Code plugin)

Ports the agent-neutral `core/eligibility` hard-rule judge and `core/policy` delegation policy to
Claude Code's `Agent`/`Task` subagent tool and plugin format. See
`docs/claude-codex-adapter-plan.md` (repo root) for the full design record, official-doc citations,
and the exact list of what is and is not enforced.

## What it does

A `PreToolUse` hook (matcher `Agent`/`Task`) intercepts every subagent spawn, discovers the
project's and user's declared agents (`.claude/agents/*.md`, `~/.claude/agents/*.md`), and checks
the call's effective model (per-call `model` override, else the agent file's `model:`, else
`inherit`) against `core/eligibility`'s hard rules using a Claude-Code-native capability snapshot
(`capabilities.json`, ported from `core/spec/model-capabilities.json`'s methodology — see
`adapters/claude-code/model-capabilities.json` for sources and collection date). A violation returns
`permissionDecision: deny` with the reason and the eligible alternatives.

## What it blocks

| Rule | Blocks when |
|---|---|
| Registered | `subagent_type` matches no `name:` in any `.claude/agents/*.md` |
| Unknown model | The effective model has no entry in `capabilities.json` |
| Context | Model's known context window is exceeded (only when the call carries a length; it rarely does) |
| Modality / tools | A task need that the hook's `tool_input` doesn't actually carry (no-op in practice) |

## What it does NOT block (platform has no field for it — not a gap in this adapter)

- **Reasoning effort.** Claude Code has no per-agent effort field; effort is a session-wide
  `/effort` setting. The guard drops `effort_implicit`/`effort_unadvertised`/`effort_cannot_disable`
  from its verdict rather than block on an axis the user cannot set per agent.
- **Service tier / free-to-paid fallback.** Not a Claude Code concept; every route is fixed to the
  one tier `core/eligibility` has verified (`normal`), so the check runs but never fires.
- **Input length and long-context surcharge.** `tool_input` on an `Agent` call carries no length
  info, matching the identical limitation already documented for the Hermes `routing-guard` plugin.

## Install

```bash
# Quick test, this session only (no marketplace needed):
claude --plugin-dir /path/to/subagent-routing-kit/adapters/claude-code/plugin

# Permanent: add a local marketplace, then install
claude plugin marketplace add /path/to/subagent-routing-kit/adapters/claude-code/plugin
claude plugin install subagent-routing-kit@<marketplace-name>
```

After install, hooks require no extra enablement in Claude Code (unlike Codex's trust-review step),
but still confirm with `/hooks` that the plugin's `PreToolUse` entry is listed and active.

## Verification status

The pure logic (`guard.py`, `agent_frontmatter.py`) and the hook entrypoint (`guard_hook.py`) have
offline unit tests (`tests/test_claude_code_routing_guard.py` in the repo) that run without Claude
Code installed. **The actual plugin wiring — manifest validity, hook discovery, and a real blocked
call — has not been verified against a live Claude Code install from this environment** (no `claude`
binary available, and a global npm install is blocked by this environment's own approval policy).
Run `claude plugin validate <path>` and a real blocked call in your own environment before trusting
this in a shared project, the same caveat the Hermes adapter's `apply_model_map.py --apply` already
carries for its own live-apply step.

## Known limitations

- Built-in Claude Code agent types without a `.claude/agents/*.md` file are indistinguishable from a
  typo to this guard (no official list of built-in names was available when this was written) —
  they will be reported as not registered. Add a file for them if this produces false positives.
- The capability snapshot is a point-in-time, hand-curated list (one model family, 2026-11-16). A
  new Claude model alias/version needs a snapshot update before it passes strict mode.
- Project-directory discovery uses `$CLAUDE_PROJECT_DIR` (falls back to the hook process's CWD).
