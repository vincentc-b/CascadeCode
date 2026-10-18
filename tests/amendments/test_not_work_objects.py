"""Amendment sidecars are not board work objects (task_026)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cascade.amendments import Amendment, write_sidecar
from cascade.board import list_board
from cascade.watchdog.loop import _active_markdown
from tests.support import add_doc, make_repo

_SIDECAR_EPIC = """\
# Epic

## Memory Layout

Baseline text.
"""


def test_amendments_not_in_list_board_or_watchdog_glob(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )

    write_sidecar(
        Amendment(
            id="",
            feature_id="feat_001",
            epic_id="epic_001",
            section="Memory Layout",
            diff_path=Path("."),
            proposed_text="Proposed.",
            rationale="Because.",
            state="pending",
            created=datetime.now(timezone.utc),
        ),
        _SIDECAR_EPIC,
        root=root,
    )

    sidecar_dir = root / "docs" / "epics" / "2_active" / "_amendments"
    assert any(sidecar_dir.glob("*.diff.md"))

    index = list_board(root)
    assert "_amendments" not in {meta.path.parts[-2] for meta in index.by_id.values()}

    active_paths = _active_markdown(root)
    assert active_paths
    assert all("_amendments" not in path.parts for path in active_paths)
    assert all(path.parent.name == "2_active" for path in active_paths)
    assert all(path.suffix == ".md" for path in active_paths)
