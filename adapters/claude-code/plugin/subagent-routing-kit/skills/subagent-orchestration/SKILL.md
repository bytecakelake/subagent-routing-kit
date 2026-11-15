---
name: subagent-orchestration
description: "Use when delegating tasks via the Agent/Task tool. Route, brief, verify workers."
version: 0.1.0
author: BCL, Hermes Agent
license: Apache-2.0
platforms: [linux, macos, windows]
metadata:
  tags: [delegation, orchestration, routing, cost, verification]
  related_skills: [claude-code]
---

# Cost- and evidence-driven subagent operation (Claude Code adapter)

Thin adapter that applies the agent-neutral policy to Claude Code's `Agent` (formerly `Task`) tool.
Policy body: `references/orchestration-policy.md`. Tier-to-variant mapping (written for a different
host; read it for the *shape* of the reasoning, not literal names): `references/routing-policy.md`.
Handoff template: `templates/task-contract.md`. Child report schema: `templates/output-contract.schema.json`
(validate returned reports against it). Read the policy body before delegating. This skill is
behavioral guidance; the companion `hooks/hooks.json` in this same plugin enforces the hard rules
that are actually structural (see below), the rest is advisory.

## When to Use

- Delegating independent research, analysis, implementation, or review via the `Agent` tool.
- Choosing a subagent and escalation path that fit task difficulty and cost.
- Single lookups, arithmetic, repetitive parsing, sequentially dependent work: spawn no agent; do it
  directly.

## Claude Code facts to check

- **Pick the subagent with `subagent_type`.** It is a `name:` from `.claude/agents/**/*.md` or
  `~/.claude/agents/`, or a built-in (`Explore`, `Plan`, `general-purpose`, ...), a managed, `--agents`
  or plugin agent (`plugin:agent`). The routing guard in this plugin can only read agent files, so it
  never blocks an unfamiliar name as "unregistered"; it judges only an observable `model`/`effort`.
- **Per-agent effort is supported.** Set `effort:` in the agent frontmatter (`low`, `medium`, `high`,
  `xhigh`, `max`; levels depend on the model); Claude Code >= v2.1.292 also accepts a per-invocation
  `effort`. It overrides the session level, but `CLAUDE_CODE_EFFORT_LEVEL` overrides both. Without it,
  the subagent uses the session level on the main model. Do not invent a `reasoning_effort:` key.
- **Model precedence:** per-call `model` (alias only) > the agent file's `model:` (alias, full ID or
  `inherit`) > `CLAUDE_CODE_SUBAGENT_MODEL` > the main conversation's model. Aliases resolve per
  provider, so `sonnet` is not the same model everywhere.
- **Omitted/`inherit` `model:` is not judged by the guard.** The effective model depends on the
  session, environment and provider, which the hook cannot see; do not assume it resolved to anything.
- **Children cannot ask questions or re-delegate.** Have them return unclear requirements as a
  blocker instead of guessing.
- **Validation through an existing agent definition is not live-call validation of a new one.** Never
  report it as such.

## Procedure

1. Follow steps 1-8 in `references/orchestration-policy.md`.
2. Pick the subagent by matching `subagent_type` exactly against an agent you know exists. If none
   fits, create an agent file or report `activation_required`.
3. Write each child contract with `templates/task-contract.md`.

## What the hard-rule guard in this plugin does and does not check

Enforced, when observable: the call's `model` override (else the discovered agent file's `model:`)
has a capability-snapshot entry (`capabilities.json` in this plugin, for Claude's own aliases and
IDs), and an observable `effort` is in that model's `supported_efforts`.
Not enforced: whether the subagent exists (built-in/managed/CLI/plugin agents are invisible to the
hook), an omitted/`inherit` model, a missing effort, provider-specific alias resolution,
modality/tool requirements per task, input length / long-context surcharge, free-to-paid fallback.
Full rationale:
`docs/claude-codex-adapter-plan.md` in the subagent-routing-kit repo.

## Sync

`references/` and `templates/` are generated copies of the repo's `core/policy/`. Do not edit them
directly: edit `core/policy/`, then run `python adapters/claude-code/sync_plugin.py`. Drift check:
`--check`.
