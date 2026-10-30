---
name: subagent-orchestration
description: "Use when delegating tasks. Route, brief, verify workers."
version: 0.3.0
author: BCL, Hermes Agent
license: Apache-2.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [delegation, orchestration, routing, cost, verification]
    related_skills: [hermes-agent, requesting-code-review]
---

# Cost- and evidence-driven subagent operation (Hermes adapter)

Thin adapter that applies the agent-neutral policy to Hermes `delegate_task`. Policy body: `references/orchestration-policy.md`. Tier-to-variant mapping: `references/routing-policy.md`. Handoff template: `templates/task-contract.md`. Read the policy body before delegating. This skill is behavioral guidance; it does not enforce a runtime router, permission control, or spend limit.

## When to Use

- Delegating independent research, analysis, implementation, or review via `delegate_task`.
- Choosing a variant, parallel scope, and escalation path that fit task difficulty and cost.
- Single lookups, arithmetic, repetitive parsing, sequentially dependent work: spawn no agent; use direct tools or `execute_code`.

## Hermes facts to check

- **Pick the route with `option`.** `option` is a route name registered in the `advanced-delegation` plugin's `model_map`; only names listed in the current tool schema are valid. Proposal JSON, past sessions, and this skill's tables are not evidence of registration.
- **Task args are `tasks=[{goal, context, option, output_schema?, images?}]`.** Never add `model`, `toolsets`, `reasoning_effort`, or `service_tier` to a task; the tool does not accept them.
- **`model_map` copies provider, model, base_url, api_key, api_mode, reasoning_effort, service_tier into the route and optionally passes fallback_providers.** Assume no other router options are usable on subagent routes.
- **Omitted reasoning effort inherits `delegation.reasoning_effort` or the parent setting.** Supported values differ per route; check the exact model's supported set. `none` means off and is invalid for mandatory-reasoning models.
- **Current OpenRouter routes do not accept `fast`/`ultrafast`.** Every proposed route uses `service_tier: normal`.
- **The route list is frozen by schema at session start.** After changing config, re-check routes in a new session.
- **Children cannot ask questions or re-delegate.** Have them return unclear requirements as a blocker instead of guessing.
- **Async delegation results arrive between turns.** Do only non-dependent work, then end the turn. Do not poll transcripts. `/new`, `/stop`, and process exit abort running children.
- **Up to 8 images pass directly via `images`.** Convert audio and video to text (transcript) or images (frame extraction) first.
- **Validation through an existing route is not live-call validation of a new route.** Never report it as such.

## Procedure

1. Follow steps 1-8 in `references/orchestration-policy.md`.
2. Choose routes with the tiers in `references/routing-policy.md` and match them exactly against the current `option` list. If missing, report `activation_required`.
3. Write each child contract with `templates/task-contract.md`.

## Sync

`references/` and `templates/` are generated copies of the repo's `core/policy/`. Do not edit them directly: edit `core/policy/`, then run `python adapters/hermes/sync_skill.py`. Drift check: `--check`.
