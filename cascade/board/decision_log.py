"""Shared append logic for Epic and Feature ## Decision log sections."""

from __future__ import annotations

import re
from datetime import date

_DEC_ID_RE = re.compile(r"dec_(\d{3})\b")


def single_line(value: str) -> str:
    return " ".join(value.split())


def append_to_decision_log(
    body: str,
    *,
    section: str,
    choice: str,
    rationale: str,
    honors: str,
    author: str,
    author_labels: dict[str, str],
    missing_section_message: str,
) -> tuple[str, str]:
    match = re.search(r"^## Decision log\s*$", body, re.MULTILINE)
    if not match:
        raise ValueError(missing_section_message)

    start = match.end()
    if start < len(body) and body[start] == "\n":
        start += 1

    next_heading = re.search(r"^## ", body[start:], re.MULTILINE)
    section_end = start + next_heading.start() if next_heading else len(body)
    section_text = body[start:section_end]

    next_num = 1
    for id_match in _DEC_ID_RE.finditer(section_text):
        next_num = max(next_num, int(id_match.group(1)) + 1)

    decision_id = f"dec_{next_num:03d}"
    label = author_labels.get(author, author)
    today = date.today().isoformat()
    section = single_line(section)
    choice = single_line(choice)
    rationale = single_line(rationale)
    honors = single_line(honors)
    block = (
        f"\n\n- `{decision_id}` · {today} · {label} · **{section}**\n"
        f"  Chose {choice}.\n"
        f"  Rationale: {rationale}\n"
        f"  Honors: {honors}.\n"
    )

    new_body = body[:section_end].rstrip() + block + body[section_end:]
    return decision_id, new_body
