"""Epic completion confirm (task_042)."""

from __future__ import annotations

import json
from pathlib import Path

from cascade.board.store import move_doc, read_doc
from cascade.boss.epic_complete import (
    confirm_epic_complete,
    epic_ready_to_close,
    on_feature_completed,
    reset_epic_close_prompt_surfaces,
    surface_epic_close_prompt,
)
from cascade.comments.store import comment
from cascade.watchdog.events import read_events
from tests.support import add_doc, make_repo


def _epic_board(tmp_path: Path, *, feat_two_completed: bool = True) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active", children=["feat_001"])
    add_doc(
        root,
        id="feat_001",
        title="Feature one",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    if feat_two_completed:
        add_doc(
            root,
            id="feat_002",
            title="Feature two",
            tier="feature",
            status="completed",
            parent="epic_001",
        )
    else:
        add_doc(
            root,
            id="feat_002",
            title="Feature two",
            tier="feature",
            status="active",
            parent="epic_001",
        )
    return root


def _war_room_toasts(root: Path, *, kind: str | None = None) -> list[dict]:
    events, _ = read_events("war_room", 0, root=root)
    out: list[dict] = []
    for event in events:
        if event.type != "Toast":
            continue
        if kind is not None and event.payload.get("kind") != kind:
            continue
        out.append(event.payload)
    return out


def test_epic_ready_when_all_features_completed(tmp_path: Path) -> None:
    root = _epic_board(tmp_path)
    assert epic_ready_to_close("epic_001", root=root) is True


def test_epic_not_ready_when_child_feature_still_active(tmp_path: Path) -> None:
    root = _epic_board(tmp_path, feat_two_completed=False)
    assert epic_ready_to_close("epic_001", root=root) is False


def test_epic_not_ready_while_completed_feature_awaits_review(tmp_path: Path) -> None:
    root = _epic_board(tmp_path)
    state = root / ".cascade" / "reviews.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps(
            {
                "feat_001": {
                    "url": "https://github.example/pull/1",
                    "source_branch": "feat/feat_001",
                    "target_branch": "epic/epic_001",
                    "forge": "github",
                    "closed": False,
                }
            }
        ),
        encoding="utf-8",
    )

    assert epic_ready_to_close("epic_001", root=root) is False


def test_human_confirm_moves_epic_and_emits_event(tmp_path: Path) -> None:
    root = _epic_board(tmp_path)

    assert confirm_epic_complete("epic_001", "human", root=root) is True

    epic = read_doc("epic_001", root=root)
    assert epic.meta.status == "completed"
    assert epic.meta.path.parent.name == "3_completed"

    events, _ = read_events("war_room", 0, root=root)
    completed = [event for event in events if event.type == "EpicCompleted"]
    assert len(completed) == 1
    assert completed[0].payload == {"epic_id": "epic_001"}
    assert completed[0].dest == "war_room"


def test_boss_confirm_refused_epic_stays_active(tmp_path: Path) -> None:
    root = _epic_board(tmp_path)

    assert confirm_epic_complete("epic_001", "boss", root=root) is False

    epic = read_doc("epic_001", root=root)
    assert epic.meta.status == "active"
    assert epic.meta.path.parent.name == "2_active"
    events, _ = read_events("war_room", 0, root=root)
    assert not any(event.type == "EpicCompleted" for event in events)


def test_human_confirm_idempotent_when_epic_already_completed(tmp_path: Path) -> None:
    root = _epic_board(tmp_path)

    assert confirm_epic_complete("epic_001", "human", root=root) is True
    assert confirm_epic_complete("epic_001", "human", root=root) is True

    events, _ = read_events("war_room", 0, root=root)
    completed = [event for event in events if event.type == "EpicCompleted"]
    assert len(completed) == 1


def test_non_human_confirm_refused_even_when_epic_already_completed(tmp_path: Path) -> None:
    root = _epic_board(tmp_path)
    assert confirm_epic_complete("epic_001", "human", root=root) is True

    assert confirm_epic_complete("epic_001", "feature_lead", root=root) is False

    events, _ = read_events("war_room", 0, root=root)
    assert len([e for e in events if e.type == "EpicCompleted"]) == 1


def test_open_human_comment_on_epic_blocks(tmp_path: Path) -> None:
    root = _epic_board(tmp_path)
    comment("epic_001", "Scope", "wait", author="human", root=root)

    assert epic_ready_to_close("epic_001", root=root) is False
    assert confirm_epic_complete("epic_001", "human", root=root) is False
    assert read_doc("epic_001", root=root).meta.status == "active"


def test_on_feature_completed_surfaces_prompt_when_last_feature_done(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active", children=["feat_001"])
    add_doc(
        root,
        id="feat_001",
        title="First",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Second",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    reset_epic_close_prompt_surfaces()
    on_feature_completed("feat_001", root=root)
    assert _war_room_toasts(root, kind="epic_ready_to_close") == []

    move_doc("feat_002", "completed", root=root)
    on_feature_completed("feat_002", root=root)
    toasts = _war_room_toasts(root, kind="epic_ready_to_close")
    assert len(toasts) == 1
    assert toasts[0]["epic_id"] == "epic_001"
    assert toasts[0]["kind"] == "epic_ready_to_close"
    assert toasts[0]["id"] == "epic_001"


def test_surface_prompt_idempotent_within_process(tmp_path: Path) -> None:
    root = _epic_board(tmp_path)
    reset_epic_close_prompt_surfaces()

    surface_epic_close_prompt("epic_001", root=root)
    surface_epic_close_prompt("epic_001", root=root)
    surface_epic_close_prompt("epic_001", root=root)

    assert len(_war_room_toasts(root, kind="epic_ready_to_close")) == 1


def test_feature_linked_by_parent_not_in_epic_children(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active", children=[])
    add_doc(
        root,
        id="feat_001",
        title="Only feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )

    assert epic_ready_to_close("epic_001", root=root) is True
    assert confirm_epic_complete("epic_001", "human", root=root) is True
