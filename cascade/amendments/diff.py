"""Unified diff generation for Epic section amendments."""

from __future__ import annotations

import difflib
import re


def extract_section_body(epic_body: str, section: str) -> str:
    """Return markdown body under ``## {section}`` until the next ``##`` heading."""

    pattern = re.compile(rf"^## {re.escape(section)}\s*$", re.MULTILINE)
    matches = list(pattern.finditer(epic_body))
    if not matches:
        raise ValueError(f"epic body missing section: {section!r}")
    if len(matches) > 1:
        raise ValueError(f"epic body has duplicate section: {section!r}")
    match = matches[0]
    start = match.end()
    if start < len(epic_body) and epic_body[start] == "\n":
        start += 1
    next_heading = re.search(r"^## ", epic_body[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(epic_body)
    return epic_body[start:end].rstrip("\n")


def unified_section_diff(
    epic_body: str,
    section: str,
    proposed_text: str,
    *,
    epic_label: str = "epic",
) -> str:
    """Build unified diff replacing the named section body with ``proposed_text``."""

    old_body = extract_section_body(epic_body, section)
    old_lines = old_body.splitlines(keepends=True)
    if old_lines and not old_lines[-1].endswith("\n"):
        old_lines[-1] = old_lines[-1] + "\n"
    new_lines = proposed_text.splitlines(keepends=True)
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] = new_lines[-1] + "\n"
    if not new_lines and not old_lines:
        new_lines = [""]

    label = f"{epic_label}/{section}"
    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=label,
        tofile=label,
        lineterm="",
    )
    body = "\n".join(diff_lines)
    if body and not body.endswith("\n"):
        body += "\n"
    title = f"<!-- Amendment: {section} -->\n"
    return title + body
