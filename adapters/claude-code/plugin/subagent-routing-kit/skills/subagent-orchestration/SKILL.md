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

- **Pick the subagent with `subagent_type`.** It must match a `name:` declared in a
  `.claude/agents/*.md` file (project or `~/.claude/agents/`), or a built-in agent type. This repo's
  routing guard (`hooks/hooks.json` in this plugin) blocks calls to names it cannot find in either
  directory — built-in types without a file are a known false positive the guard cannot resolve
  (no official list of built-in names was confirmed when this adapter was written; see
  `docs/claude-codex-adapter-plan.md` in the kit's own repo).
- **The agent's `model:` field is the only per-agent override Claude Code exposes.** There is no
  per-agent reasoning-effort field — effort is a session-wide `/effort` setting, not a route property.
  Do not invent a `reasoning_effort:` frontmatter key; Claude Code ignores it and the routing guard
  does not check it for this reason.
- **A per-call `model` override on the `Agent` tool call beats the agent file's own `model:`.** The
  guard checks whichever one actually applies.
- **Omitted `model:` inherits the session's current model.** The guard cannot validate what that
  resolves to and treats it as `inherit` (unknown model) — strict mode blocks it, because the actual
  model at run time is not knowable from the call alone.
- **Children cannot ask questions or re-delegate.** Have them return unclear requirements as a
  blocker instead of guessing.
- **Validation through an existing agent definition is not live-call validation of a new one.** Never
  report it as such.

## Procedure

1. Follow steps 1-8 in `references/orchestration-policy.md`.
2. Pick the subagent by matching `subagent_type` exactly against a declared `.claude/agents/*.md`
   `name:`. If none fits, create one or report `activation_required`.
3. Write each child contract with `templates/task-contract.md`.

## What the hard-rule guard in this plugin does and does not check

Enforced: the chosen `subagent_type` is declared somewhere in `.claude/agents/`, and its effective
model has a capability-snapshot entry (`capabilities.json` in this plugin, ported from
`core/spec/model-capabilities.json`'s methodology but for Claude's own model aliases).
Not enforced (platform has no native field for it, or the hook call carries no such information):
reasoning effort, modality/tool requirements per task, input length / long-context surcharge,
free-to-paid fallback (Claude Code has no free-tier model concept). Full rationale:
`docs/claude-codex-adapter-plan.md` in the subagent-routing-kit repo.

## Sync

`references/` and `templates/` are generated copies of the repo's `core/policy/`. Do not edit them
directly: edit `core/policy/`, then run `python adapters/claude-code/sync_plugin.py`. Drift check:
`--check`.
