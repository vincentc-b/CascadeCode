"""The brief editor preserves the identity and untouched content of a brief."""

from dataclasses import replace
from datetime import date
from pathlib import Path

from cascade.board.types import WorkDoc, WorkMeta
from cascade.brief_edit import (
    BriefEditRequest,
    BriefEditSource,
    brief_edit_unchanged,
    load_brief_edit,
    render_brief_edit,
)


def test_edit_preserves_identity_metadata_and_unrelated_sections() -> None:
    path = Path("docs/epics/1_backlog/epic_999_example.md")
    original = WorkDoc(
        meta=WorkMeta(
            id="epic_999",
            title="Original title",
            tier="epic",
            status="backlog",
            parent=None,
            children=[],
            depends_on=[],
            owners=["epic_manager"],
            skills=[],
            parent_rev=None,
            created=date(2026, 10, 1),
            updated=date(2026, 10, 2),
            path=path,
            provider="codex",
            models={"epic_manager": "model-a"},
            reasoning={"epic_manager": "high"},
        ),
        body=(
            "# Original title\n\n"
            "## Intent\n\nOld intent.\n\n"
            "## Success criteria\n\nOld criterion.\n\n"
            "## Cross-module constraints\n\nOld constraint.\n\n"
            "## Custom notes\n\nKeep this exact note.\n"
        ),
        sha="source-revision",
    )
    loaded = load_brief_edit(original)
    assert loaded["source"] == BriefEditSource("epic_999", path, "source-revision")
    assert loaded["intent"] == "Old intent."
    assert loaded["success_criteria"] == "Old criterion."
    assert loaded["constraints"] == "Old constraint."

    edit = BriefEditRequest(
        title="Revised title",
        intent="New intent.",
        success_criteria="New criterion.",
        constraints="New constraint.",
        provider="codex",
        models={"epic_manager": "model-b"},
        reasoning={},
        cleared_reasoning=frozenset({"epic_manager"}),
        source=loaded["source"],
        original=original,
    )
    changed = render_brief_edit(edit)
    assert changed.meta.id == original.meta.id
    assert changed.meta.path == path
    assert changed.meta.created == original.meta.created
    assert changed.meta.status == "backlog"
    assert changed.meta.title == "Revised title"
    assert changed.meta.reasoning is None
    assert changed.body.startswith("# Revised title\n")
    assert "New intent." in changed.body
    assert "New criterion." in changed.body
    assert "New constraint." in changed.body
    assert "## Custom notes\n\nKeep this exact note.\n" in changed.body
    assert brief_edit_unchanged(edit) is False

    same = BriefEditRequest(
        title=original.meta.title,
        intent=loaded["intent"],
        success_criteria=loaded["success_criteria"],
        constraints=loaded["constraints"],
        provider="codex",
        models={"epic_manager": "model-a"},
        reasoning={"epic_manager": "high"},
        cleared_reasoning=frozenset(),
        source=loaded["source"],
        original=original,
    )
    assert brief_edit_unchanged(same) is True

    revised_notes = render_brief_edit(
        replace(edit, additional_markdown="## Custom notes\n\nRevised note.")
    )
    assert "## Custom notes\n\nRevised note." in revised_notes.body
    assert "Keep this exact note." not in revised_notes.body
