"""Frontmatter reader for Claude Code agent files (`.claude/agents/**/*.md`).

Stdlib only (this module ships inside the plugin, where this repo's dependencies are not
installed), so it is NOT a full YAML parser. It covers the subset agent files use: top-level
`key: value` lines with plain, single- or double-quoted, flow (`[..]`/`{..}`), block (`|`/`>`)
and nested/list values. Values of nested/list/flow/block keys are kept as raw text or a list of
raw items; only scalar `name`, `description`, `model` and `effort` are consumed by the guard.

It refuses only what was measured to fail in the real parser (`claude plugin validate
.claude/agents`, Claude Code 2.1.325: "YAML frontmatter failed to parse ... At runtime this agent
does not load at all"): an unterminated quoted string, tab indentation, and a stray non-mapping
line. The same CLI ACCEPTED `description: Use when: x`, an unclosed `[Read, Grep` flow list and a
leading `@`, so those are tolerated here and not guessed to be errors. A missing closing `---` fence
passes validation but is treated as "no frontmatter" here (unobserved). The detection is an
approximation (duplicate keys etc. are not flagged); when a file is rejected the guard has no
observation for that agent and never invents one.
"""
from __future__ import annotations

import json
import re
from typing import Optional

_FENCE = "---"
_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*):(?:[ \t]+(.*))?$")
_MAX_NAME = 256


class FrontmatterError(ValueError):
    """The frontmatter would not parse as YAML (so Claude Code skips the file)."""


def _strip_comment(text: str) -> str:
    m = re.search(r"(^|\s)#", text)
    return text[:m.start()].rstrip() if m else text.rstrip()


def _double_quoted(text: str) -> str:
    # find the closing unescaped quote
    i = 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            rest = text[i + 1:].strip()
            if rest and not rest.startswith("#"):
                raise FrontmatterError(f"unexpected text after quoted value: {rest!r}")
            try:
                return json.loads(text[:i + 1])
            except ValueError:
                return text[1:i].replace('\\"', '"').replace("\\\\", "\\")
        i += 1
    raise FrontmatterError("unterminated double-quoted string")


def _single_quoted(text: str) -> str:
    i = 1
    while i < len(text):
        if text[i] == "'":
            if text[i + 1:i + 2] == "'":
                i += 2
                continue
            rest = text[i + 1:].strip()
            if rest and not rest.startswith("#"):
                raise FrontmatterError(f"unexpected text after quoted value: {rest!r}")
            return text[1:i].replace("''", "'")
        i += 1
    raise FrontmatterError("unterminated single-quoted string")


def _plain(text: str) -> str:
    return _strip_comment(text)  # `a: b` inside a plain scalar is accepted by Claude Code 2.1.325


def _value(first: str, cont: list):
    """Interpret one key's value given the text after `key:` and its continuation lines."""
    first = first.strip()
    if first[:1] in ("|", ">"):
        return " ".join(c.strip() for c in cont if c.strip())
    if first == "" or first.startswith("#"):
        items = [c.strip() for c in cont if c.strip() and not c.strip().startswith("#")]
        if not items:
            return ""
        if all(i.startswith("- ") or i == "-" for i in items):
            return [i[1:].strip() for i in items]
        return " ".join(items)  # nested mapping: raw text, not consumed by the guard
    if first[0] == '"':
        return _double_quoted(" ".join([first] + [c.strip() for c in cont]))
    if first[0] == "'":
        return _single_quoted(" ".join([first] + [c.strip() for c in cont]))
    if first[0] in "[{":
        return _strip_comment(" ".join([first] + [c.strip() for c in cont]))  # raw; unclosed accepted
    return " ".join([_plain(first)] + [_plain(c.strip()) for c in cont if c.strip()])


def parse_frontmatter_strict(text: str) -> Optional[dict]:
    """Return the frontmatter mapping, None when the file has no (closed) frontmatter,
    or raise FrontmatterError when it would not parse."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != _FENCE:
        return None  # the opening fence must be the file's first line
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == _FENCE), None)
    if end is None:
        return None  # no closing fence: not frontmatter (validate passes it; unobserved here)
    body = lines[1:end]
    out: dict = {}
    i = 0
    while i < len(body):
        line = body[i]
        i += 1
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[0] in " \t":
            raise FrontmatterError(f"unexpected indentation: {line!r}")
        m = _KEY.match(line.rstrip())
        if not m:
            raise FrontmatterError(f"not a `key: value` line: {line!r}")
        key, first = m.group(1), m.group(2) or ""
        cont = []
        while i < len(body):
            nxt = body[i]
            blank = not nxt.strip()
            indented = nxt[:1] in (" ", "\t")
            listy = first.strip() == "" and nxt.startswith("- ")
            if not (blank or indented or listy):
                break
            if "\t" in nxt[:len(nxt) - len(nxt.lstrip())]:
                raise FrontmatterError(f"tab indentation: {nxt!r}")
            if not blank:
                cont.append(nxt)
            i += 1
        out[key] = _value(first, cont)
    return out


def parse_frontmatter(text: str) -> dict:
    """Lenient wrapper: {} when there is no (parseable) frontmatter."""
    try:
        return parse_frontmatter_strict(text) or {}
    except FrontmatterError:
        return {}


def _scalar(meta: dict, key: str) -> Optional[str]:
    value = meta.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def read_agent_file(path) -> Optional[dict]:
    """Read one agent definition file; None if Claude Code would skip it.

    Skipped per the sub-agents doc: no frontmatter, unparseable YAML, no `name`, a `name` that
    starts with `-`, contains `:` or exceeds 256 characters, or no `description`.
    """
    try:
        text = path.read_text(encoding="utf-8")
        meta = parse_frontmatter_strict(text)
    except (OSError, UnicodeDecodeError, FrontmatterError):
        return None
    if not meta:
        return None
    name = _scalar(meta, "name")
    if not name or name.startswith("-") or ":" in name or len(name) > _MAX_NAME:
        return None
    if not _scalar(meta, "description") and not meta.get("description"):
        return None
    return {"name": name, "model": _scalar(meta, "model"), "effort": _scalar(meta, "effort"),
            "description": meta.get("description")}
