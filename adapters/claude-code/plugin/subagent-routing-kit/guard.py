"""Check a Claude Code `Agent`/`Task` call against core/eligibility hard rules.

Mirrors adapters/hermes/plugin/routing-guard/guard.py, but Claude Code has no
central route registry to read: declared routes are discovered by scanning the
project's and user's `.claude/agents/**/*.md` files at call time. Agents that are
not files (built-in, managed, `--agents`, plugin) cannot be seen, so "not
registered" is never a verdict here.
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
# Per-agent effort IS supported: the agent frontmatter `effort:` field (low|medium|high|xhigh|max,
# "available levels depend on the model") and, on Claude Code >= v2.1.292, a per-invocation
# `effort` parameter on the Agent call (code.claude.com/docs/en/sub-agents, "Choose an effort
# level"). When either is observed it is checked against the snapshot (EFFORT_UNADVERTISED /
# EFFORT_CANNOT_DISABLE). Only the *absence* of an effort is exempt: the subagent then falls back
# to the session level (/effort, --effort, CLAUDE_CODE_EFFORT_LEVEL), which this hook cannot see,
# and blocking every agent that omits the field would be a policy this adapter does not impose.
EFFORT_CODES_NOT_APPLICABLE = frozenset({rules.EFFORT_IMPLICIT})
INHERIT_MODEL = "inherit"  # sentinel: no `model:` field, the subagent inherits the session model


def _ancestors_to_repo_root(start: pathlib.Path) -> list:
    """`start` and its parents up to and including the first directory that holds `.git`.

    Claude Code scans every `.claude/agents/` between the working directory and the repository
    root. Without a `.git` marker only `start` itself is scanned (no unbounded walk to `/`).
    """
    chain = []
    for d in [start, *start.parents]:
        chain.append(d)
        if (d / ".git").exists():
            return chain
    return [start]


def agent_search_dirs(project_dir, home_dir, cwd=None) -> list:
    """Observable agent directories, closest first: project chain (from cwd, then
    project_dir), then `~/.claude/agents`.

    NOT observable from a hook, so never scanned: managed-settings agents, the `--agents` CLI
    flag, plugin `agents/` directories, `--add-dir` directories, and built-in agent types.
    """
    dirs: list = []
    for base in (cwd, project_dir):
        if not base:
            continue
        for d in _ancestors_to_repo_root(pathlib.Path(base)):
            cand = d / ".claude" / "agents"
            if cand not in dirs:
                dirs.append(cand)
    if home_dir:
        cand = pathlib.Path(home_dir) / ".claude" / "agents"
        if cand not in dirs:
            dirs.append(cand)
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


def _declared_model(agent: Optional[Mapping]) -> Optional[str]:
    model = ((agent or {}).get("model") or "").strip()
    return None if not model or model == INHERIT_MODEL else model


def guard_call(tool_name: str, tool_input: Mapping, agents: Mapping, caps: Mapping, *,
               strict: bool = True) -> Optional[str]:
    """Return a block message, or None to let the call through.

    Only what the hook can observe is judged: a per-call `model` alias, else the discovered
    agent file's `model:`; plus an `effort` from the call or the file. A subagent that is not a
    discovered file (built-in, managed, --agents, plugin) is NOT rejected as unregistered, and an
    omitted/`inherit` model is NOT judged: its effective model depends on the session,
    CLAUDE_CODE_SUBAGENT_MODEL and the provider, none of which reach the hook.
    """
    if tool_name not in TOOL_NAMES or not isinstance(tool_input, Mapping):
        return None
    chosen = str(tool_input.get("subagent_type") or "").strip()
    if not chosen:
        return None  # not a real subagent spawn (or a shape this adapter doesn't recognize)

    agent = agents.get(chosen)
    override_model = str(tool_input.get("model") or "").strip()
    effective_model = override_model or _declared_model(agent)
    if not effective_model:
        return None  # nothing observable to judge
    effort = str(tool_input.get("effort") or (agent or {}).get("effort") or "").strip() or None

    routes = [rules.Route(chosen, effective_model, effort, SERVICE_TIER)]
    for name, other in agents.items():
        if name != chosen:
            routes.append(rules.Route(name, _declared_model(other) or INHERIT_MODEL,
                                      (other.get("effort") or None), SERVICE_TIER))
    names = [r.name for r in routes]
    decision = rules.evaluate(
        rules.Task(id="t0", needs_tools=True), routes, caps, registered=names)
    reasons = [r for r in decision.rejected.get(chosen, ()) if r not in EFFORT_CODES_NOT_APPLICABLE]
    if not reasons:
        return None
    if not strict and set(reasons) == {rules.UNKNOWN_MODEL}:
        logger.warning("subagent-routing-kit: %s has no capability-snapshot entry; passing", chosen)
        return None

    # Alternatives are other *discovered* agents with an explicit, known, passing model. Agents
    # that inherit the session model are unverifiable, so they are not offered as alternatives.
    alternatives = [r.name for r in routes if r.name != chosen
                    and not [c for c in decision.rejected.get(r.name, ()) if c not in EFFORT_CODES_NOT_APPLICABLE]]
    lines = [f"Agent call blocked by routing hard rules (subagent-routing-kit): "
             f"'{chosen}' -> model '{effective_model}'" + (f", effort '{effort}'" if effort else ""),
             "- " + ", ".join(reasons)]
    if rules.UNKNOWN_MODEL in reasons:
        lines.append("  Model is missing from the plugin's capabilities.json (copy of "
                     "adapters/claude-code/model-capabilities.json). "
                     "Refresh the snapshot, or set ROUTING_GUARD_STRICT_UNKNOWN_MODEL=false to warn instead of block.")
    if rules.EFFORT_UNADVERTISED in reasons or rules.EFFORT_CANNOT_DISABLE in reasons:
        lines.append("  Effort is not in the snapshot's supported_efforts for this model "
                     "(Claude Code accepts low, medium, high, xhigh, max; levels depend on the model).")
    lines.append("  Alternatives: " + (", ".join(sorted(alternatives)) if alternatives
                 else "none discovered; do the work directly as the parent or change the model/effort"))
    lines.append("Model recommendations cannot override this verdict.")
    return "\n".join(lines)
