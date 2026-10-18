"""Append-only ## Amendment log entries on Epic bodies."""

from __future__ import annotations

import re
from datetime import date

from cascade.board.decision_log import single_line


def append_to_amendment_log(
    body: str,
    *,
    amd_id: str,
    feature_id: str,
    section: str,
    outcome: str,
    note: str,
    missing_section_message: str = "epic body missing ## Amendment log section",
) -> str:
    """Append one amendment resolution line; return the updated epic body."""

    match = re.search(r"^## Amendment log\s*$", body, re.MULTILINE)
    if match is None:
        raise ValueError(missing_section_message)

    start = match.end()
    if start < len(body) and body[start] == "\n":
        start += 1

    next_heading = re.search(r"^## ", body[start:], re.MULTILINE)
    section_end = start + next_heading.start() if next_heading else len(body)
    section_text = body[start:section_end]

    placeholder = section_text.strip()
    if placeholder in {"None.", "_(empty)_", "None yet."}:
        section_text = "\n"

    today = date.today().isoformat()
    section = single_line(section)
    outcome = single_line(outcome)
    note = single_line(note)
    block = (
        f"\n\n- `{amd_id}` · {today} · **{outcome}** · {feature_id} · **{section}**\n"
        f"  {note}\n"
    )

    return body[:section_end].rstrip() + block + body[section_end:]
