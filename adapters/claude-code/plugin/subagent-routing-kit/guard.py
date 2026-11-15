"""Check a Claude Code `Agent`/`Task` call against core/eligibility hard rules.

Mirrors adapters/hermes/plugin/routing-guard/guard.py, but Claude Code has no
central route registry to read: the registered routes are discovered by
scanning the project's and user's `.claude/agents/*.md` files at call time.
See docs/claude-codex-adapter-plan.md for exactly which core/eligibility codes
this adapter can and cannot enforce, and why.

Stdlib only. This module is pure logic (no Claude Code import) so it can be
unit-tested directly.
"""
from __future__ import annotations

import logging
import pathlib
from typing import Iterable, Mapping, Optional

try:  # loaded as part of the plugin package
    from . import eligibility_rules as rules
    from . import agent_frontmatter as frontmatter
except ImportError:  # standalone run / tests with the plugin dir on sys.path
    import eligibility_rules as rules  # type: ignore[no-redef]
    import agent_frontmatter as frontmatter  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# Task was renamed to Agent in Claude Code v2.1.63; both still appear depending on version
# (code.claude.com/docs/en/sub-agents, 2026-11-16).
TOOL_NAMES = frozenset({"Agent", "Task"})
# Claude Code has no native service-tier concept; fixing every route to the one Hermes/
# OpenRouter tier that core/eligibility has verified keeps that check structurally present
# but always passing, instead of silently skipping it.
SERVICE_TIER = "normal"
# core/eligibility checks these using route.reasoning_effort, but neither the agent
# frontmatter nor the Agent-tool call schema has a field for it (confirmed against
# code.claude.com/docs/en/sub-agents and the Agent SDK Python reference, 2026-11-16).
# Blocking on an axis the user cannot set would be unactionable, so these codes are
# dropped from the verdict for this adapter only.
EFFORT_CODES_NOT_APPLICABLE = frozenset({
    rules.EFFORT_IMPLICIT, rules.EFFORT_CANNOT_DISABLE, rules.EFFORT_UNADVERTISED,
})
INHERIT_MODEL = "inherit"  # sentinel: no `model:` field, the subagent inherits the session model


def agent_search_dirs(project_dir, home_dir) -> list:
    """Directories to scan, most specific first (matches Claude Code's own precedence)."""
    dirs = []
    if project_dir:
        dirs.append(pathlib.Path(project_dir) / ".claude" / "agents")
    if home_dir:
        dirs.append(pathlib.Path(home_dir) / ".claude" / "agents")
    return dirs


def discover_agents(search_dirs: Iterable[pathlib.Path]) -> dict:
    """Scan `*.md` under each directory (recursively). First directory wins on name clash."""
    found: dict = {}
    for base in search_dirs:
        base = pathlib.Path(base)
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            agent = frontmatter.read_agent_file(path)
            if agent and agent["name"] not in found:
                found[agent["name"]] = agent
    return found


def routes_from_agents(agents: Mapping) -> list:
    return [rules.Route(name, agent.get("model") or INHERIT_MODEL, None, SERVICE_TIER)
            for name, agent in agents.items()]


def guard_call(tool_name: str, tool_input: Mapping, agents: Mapping, caps: Mapping, *,
               strict: bool = True) -> Optional[str]:
    """Return a block message, or None to let the call through."""
    if tool_name not in TOOL_NAMES or not isinstance(tool_input, Mapping):
        return None
    chosen = str(tool_input.get("subagent_type") or "").strip()
    if not chosen:
        return None  # not a real subagent spawn (or a shape this adapter doesn't recognize)

    routes = routes_from_agents(agents)
    names = [r.name for r in routes]
    by_name = {r.name: r for r in routes}
    if chosen not in by_name:
        return (f"Agent call blocked by routing hard rules (subagent-routing-kit)\n"
                f"- '{chosen}' is not declared in any .claude/agents/*.md file ({rules.ROUTE_NOT_REGISTERED}).\n"
                f"  Known agents: {', '.join(sorted(names)) if names else 'none found'}\n"
                "Create the agent file or choose a declared one. Model recommendations cannot override this verdict.")

    override_model = str(tool_input.get("model") or "").strip()
    if override_model:
        routes = [rules.Route(r.name, override_model, None, SERVICE_TIER) if r.name == chosen else r
                  for r in routes]
    decision = rules.evaluate(
        rules.Task(id="t0", needs_tools=True), routes, caps, registered=names)
    reasons = [r for r in decision.rejected.get(chosen, ()) if r not in EFFORT_CODES_NOT_APPLICABLE]
    if not reasons:
        return None
    if not strict and set(reasons) == {rules.UNKNOWN_MODEL}:
        logger.warning("subagent-routing-kit: %s has no capability-snapshot entry; passing", chosen)
        return None

    effective_model = override_model or by_name[chosen].model or INHERIT_MODEL
    # core's own decision.eligible does not know about EFFORT_CODES_NOT_APPLICABLE, so every
    # native route (all of which have reasoning_effort=None) would show rejected there. Recompute
    # eligibility here with the same adapter-specific exemption applied to every candidate.
    alternatives = [r.name for r in routes if r.name != chosen
                     and not [c for c in decision.rejected.get(r.name, ()) if c not in EFFORT_CODES_NOT_APPLICABLE]]
    lines = [f"Agent call blocked by routing hard rules (subagent-routing-kit): "
             f"'{chosen}' -> model '{effective_model}'",
             "- " + ", ".join(reasons)]
    if reasons == [rules.UNKNOWN_MODEL]:
        lines.append("  Model is missing from adapters/claude-code/model-capabilities.json. "
                      "Refresh the snapshot, or set ROUTING_GUARD_STRICT_UNKNOWN_MODEL=false to warn instead of block.")
    lines.append("  Alternatives: " + (", ".join(sorted(alternatives)) if alternatives
                 else "none; do the work directly as the parent or change the agent's model"))
    lines.append("Model recommendations cannot override this verdict.")
    return "\n".join(lines)
