"""Minimal YAML-frontmatter reader for Claude Code `.claude/agents/*.md` files.

Stdlib only (this module ships inside the plugin, where this repo's dependencies
are not installed). Supports only the flat scalar `key: value` lines Claude Code
agent frontmatter actually uses (`name`, `description`, `model`, ...). Lists,
nested maps, and multi-line scalars are not parsed; lines that don't match the
simple pattern are skipped rather than guessed at.
"""
from __future__ import annotations

import re
from typing import Optional

_FENCE = "---"
_KV = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")


def parse_frontmatter(text: str) -> dict:
    """Parse the `--- ... ---` block at the top of the file into a flat dict."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return {}
    out: dict = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == _FENCE:
            break
        if not stripped or stripped.startswith("#"):
            continue
        m = _KV.match(line)
        if not m:
            continue  # nested/list value; not needed for the fields this adapter reads
        key, value = m.group(1), m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def read_agent_file(path) -> Optional[dict]:
    """Read one agent definition file. Returns None if it has no usable frontmatter.

    `name` and `description` are required by Claude Code; a file missing `name`
    is not a valid agent definition, so it is skipped here too.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta = parse_frontmatter(text)
    name = (meta.get("name") or "").strip()
    if not name:
        return None
    return {"name": name, "model": (meta.get("model") or "").strip() or None,
            "description": meta.get("description")}
