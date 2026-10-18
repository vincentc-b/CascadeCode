"""Epic record_decision tool."""

from __future__ import annotations

from pathlib import Path

import cascade.epic.decisions  # noqa: F401 — registers record_decision
from cascade.board.store import read_doc
from cascade.epic.decisions import record_decision
from tests.support import add_doc, make_repo


def _epic(root: Path):
    return add_doc(root, id="epic_001", title="Mine", tier="epic", status="active")


def test_record_decision_first_and_second(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _epic(root)

    first = record_decision(
        "Macro-architecture",
        "local git",
        "matches DESIGN.md",
        "DESIGN.md §2",
        epic_id="epic_001",
        root=root,
    )
    assert first == "dec_001"

    doc = read_doc("epic_001", root=root)
    assert "`dec_001`" in doc.body
    assert "**Macro-architecture**" in doc.body
    assert "Chose local git." in doc.body
    assert "Rationale: matches DESIGN.md" in doc.body
    assert "Honors: DESIGN.md §2." in doc.body
    assert "Epic Architect" in doc.body

    second = record_decision(
        "Lifecycle",
        "backlog only",
        "human activates",
        "§5.0",
        epic_id="epic_001",
        root=root,
        author="epic_manager",
    )
    assert second == "dec_002"

    doc = read_doc("epic_001", root=root)
    assert "`dec_001`" in doc.body
    assert "`dec_002`" in doc.body
    assert "Epic Manager" in doc.body
    assert "## Amendment log" in doc.body
    assert "None." in doc.body.split("## Amendment log")[1]


def test_record_decision_sanitizes_newlines(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _epic(root)
    record_decision(
        "Macro\n## Fake",
        "local\ngit",
        "matches\nDESIGN",
        "§2\ninject",
        epic_id="epic_001",
        root=root,
    )
    doc = read_doc("epic_001", root=root)
    log_section = doc.body.split("## Decision log")[1].split("## Amendment log")[0]
    assert not any(line.lstrip().startswith("## Fake") for line in log_section.splitlines())
    assert "Chose local git." in doc.body
    assert "Rationale: matches DESIGN" in doc.body


def test_record_decision_after_dec_010(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    epic = _epic(root)
    epic.body = epic.body.replace(
        "## Decision log\n\nNone yet.",
        "## Decision log\n\n- `dec_010` · 2026-01-01 · Epic Architect · **Seed**\n"
        "  Chose x.\n"
        "  Rationale: y\n"
        "  Honors: z.\n\n"
        "## Decoy\n\n- `dec_099` outside log\n",
    )
    from cascade.board.store import write_doc

    write_doc(epic, root=root)
    next_id = record_decision("Next", "a", "b", "c", epic_id="epic_001", root=root)
    assert next_id == "dec_011"
