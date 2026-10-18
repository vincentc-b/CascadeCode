"""Replace Epic markdown section bodies for amendment accept."""

from __future__ import annotations

import re

from cascade.amendments.diff import extract_section_body


def replace_section_body(epic_body: str, section: str, new_text: str) -> str:
    """Return ``epic_body`` with the ``## {section}`` body replaced by ``new_text``."""

    _ = extract_section_body(epic_body, section)
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

    replacement = new_text.rstrip("\n")
    if next_heading is not None or end < len(epic_body):
        replacement = replacement + "\n"

    return epic_body[:start] + replacement + epic_body[end:]
