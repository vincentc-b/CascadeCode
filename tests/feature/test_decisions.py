"""Feature record_decision tool."""

from __future__ import annotations

from pathlib import Path

import pytest

import cascade.feature.decisions  # noqa: F401 — registers record_decision
from cascade.board.decision_log import append_to_decision_log
from cascade.board.store import read_doc, write_doc
from cascade.feature.guard import FeatureToolDenied
from cascade.feature.registry import feature_tools
from cascade.feature.decisions import record_decision
from cascade.feature.wiring import load_feature_tools
from tests.support import add_doc, make_repo


def _feature(root: Path):
    epic = add_doc(root, id="epic_001", title="Parent", tier="epic", status="active")
    return add_doc(
        root,
        id="feat_001",
        title="Mine",
        tier="feature",
        status="active",
        parent="epic_001",
    )


def test_record_decision_registers_on_import():
    load_feature_tools()
    assert "record_decision" in feature_tools()


def test_record_decision_first_and_second(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _feature(root)

    first = record_decision(
        "API contracts",
        "scoped docs only",
        "matches DESIGN.md",
        "parent epic §2",
        feature_id="feat_001",
        root=root,
    )
    assert first == "dec_001"

    doc = read_doc("feat_001", root=root)
    assert "`dec_001`" in doc.body
    assert "**API contracts**" in doc.body
    assert "Chose scoped docs only." in doc.body
    assert "Rationale: matches DESIGN.md" in doc.body
    assert "Honors: parent epic §2." in doc.body
    assert "Feature Architect" in doc.body

    second = record_decision(
        "Scope",
        "tasks only",
        "human activates",
        "§5.0",
        feature_id="feat_001",
        root=root,
        author="feature_lead",
    )
    assert second == "dec_002"

    doc = read_doc("feat_001", root=root)
    assert "`dec_001`" in doc.body
    assert "`dec_002`" in doc.body
    assert "Feature Lead" in doc.body


def test_record_decision_monotonic_after_dec_010(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    feature = _feature(root)
    feature.body = feature.body.replace(
        "## Decision log\n\nNone yet.",
        "## Decision log\n\n- `dec_010` · 2026-01-01 · Feature Architect · **Seed**\n"
        "  Chose x.\n"
        "  Rationale: y\n"
        "  Honors: z.\n\n"
        "## Decoy\n\n- `dec_099` outside log\n",
    )
    write_doc(feature, root=root)
    next_id = record_decision("Next", "a", "b", "c", feature_id="feat_001", root=root)
    assert next_id == "dec_011"


def test_record_decision_missing_section() -> None:
    with pytest.raises(ValueError, match="feature body missing ## Decision log"):
        append_to_decision_log(
            "# Title\n\n## Scope\n\nNo decision log.\n",
            section="X",
            choice="a",
            rationale="b",
            honors="c",
            author="feature_architect",
            author_labels={"feature_architect": "Feature Architect"},
            missing_section_message="feature body missing ## Decision log section",
        )


def test_record_decision_does_not_write_epic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _feature(root)
    epic_before = read_doc("epic_001", root=root)

    record_decision(
        "Scope",
        "local only",
        "test isolation",
        "DESIGN",
        feature_id="feat_001",
        root=root,
    )

    epic_after = read_doc("epic_001", root=root)
    assert epic_after.body == epic_before.body
    assert "dec_001" not in epic_after.body

    epic = read_doc("epic_001", root=root)
    with pytest.raises(FeatureToolDenied):
        from cascade.feature.scoped_docs import feature_write_doc

        feature_write_doc(epic, feature_id="feat_001", root=root)
