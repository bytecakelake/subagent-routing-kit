---
name: subagent-orchestration
description: Use when delegating work to Codex subagents. Route, brief, and verify workers.
---

# Cost- and evidence-driven subagent operation (Codex adapter)

Thin adapter that applies the agent-neutral policy to Codex `spawn_agent`. Policy body: `references/orchestration-policy.md`. Tier-to-variant mapping: `references/routing-policy.md`. Handoff template: `templates/task-contract.md`. Child report schema: `templates/output-contract.schema.json`. Read the policy body before delegating. This skill is behavioral guidance. The bundled hook checks requested model settings only (see "What the hook checks"); it is not a spend limit or a security boundary.

## When to Use

- Delegating independent research, analysis, implementation, or review to subagents.
- Choosing model, reasoning effort, parallel scope, and escalation path that fit task difficulty and cost.
- Single lookups, arithmetic, or sequentially dependent work: spawn no agent.

## Codex facts to check (do not assume)

- **`spawn_agent` fields differ by multi-agent version.** V1 takes `message` or `items`, `agent_type`, `fork_context`, `model`, `reasoning_effort`. V2 requires `task_name` and `message` and takes `agent_type`, `fork_turns`, `model`, `reasoning_effort`. `model`/`reasoning_effort` may be hidden from the tool schema entirely. Use only fields present in the tool schema you are shown.
- **No `service_tier` parameter exists on `spawn_agent`.** Speed tier is not part of routing here.
- **A custom agent can override model settings.** `agent_type` selects a role; a custom agent file (`.codex/agents/*.toml`, `name`, `model`, `model_reasoning_effort`) may set the model after the call's own values. Defaults can also come from `[agents]` in `config.toml` (`default_subagent_model`, `default_subagent_reasoning_effort`). The final model and effort are therefore not something you can read off the call.
- **Prefer a custom agent that sets both `model` and `model_reasoning_effort`** for each route you want, then pick it with `agent_type`. This makes the setting visible to the hook and to the user.
- **Models come from the CLI's catalog.** The hook's snapshot (`scripts/capabilities.json`) is a copy of the bundled catalog of one CLI version. A model absent from it is reported as unknown, not as ineligible by cost.

## What the hook checks (and what it does not)

- The hook is a `PreToolUse` hook on `spawn_agent` (matcher also accepts `Agent`). Codex skips plugin hooks until the user reviews and trusts them in `/hooks`; if it is untrusted, nothing is checked.
- It blocks when any candidate setting (the call's, or a matching custom agent file's) names an unknown model, an effort the snapshot does not list for that model, `none`, or an image input for a text-only model.
- It reports **eligibility unknown** when the model or effort is omitted, or `agent_type` names a role it cannot read (built-in roles, `config.toml` roles). Unknown calls are blocked by default; `SUBAGENT_ROUTING_UNKNOWN=allow` lets them through.
- It does not check input length, tool needs, approval, write-scope overlap, service tier, or cost. Those policy rules stay your responsibility.
- A passing check means the requested settings are in the snapshot. It does not prove which model the subagent finally ran with.

## Procedure

1. Follow steps 1-8 in `references/orchestration-policy.md`.
2. Choose tiers with `references/routing-policy.md`, then express the choice as a custom agent or explicit `model` + `reasoning_effort` that exist in the snapshot. If none fit, say so instead of guessing.
3. Fill `templates/task-contract.md` for every child and require reports matching `templates/output-contract.schema.json`.
4. If the hook blocks a call, change the route or do the work directly. Do not retry the same arguments.
