"""Feature rollup and closeout (task_041)."""

from __future__ import annotations

from pathlib import Path

from cascade.board.store import read_doc
from cascade.boss.rollup import on_task_merged, try_complete_feature, write_closeout
from cascade.comments.store import comment, resolve_comment
from cascade.watchdog.events import read_events
from tests.support import add_doc, make_repo


def _rollup_board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001", "task_002"],
    )
    add_doc(
        root,
        id="task_001",
        title="Task one",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    add_doc(
        root,
        id="task_002",
        title="Task two",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    return root


def test_try_complete_feature_idempotent_when_already_completed(tmp_path: Path) -> None:
    root = _rollup_board(tmp_path)
    write_closeout("feat_001", "Done.", root=root)

    assert try_complete_feature("feat_001", root=root) is True
    assert try_complete_feature("feat_001", root=root) is True

    epic_events, _ = read_events("epic_001", 0, root=root)
    completed = [event for event in epic_events if event.type == "FeatureCompleted"]
    assert len(completed) == 1


def test_success_moves_feature_and_emits_event(tmp_path: Path) -> None:
    root = _rollup_board(tmp_path)
    write_closeout("feat_001", "All tasks landed; feature is done.", root=root)

    assert try_complete_feature("feat_001", root=root) is True

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "completed"
    assert feature.meta.path.parent.name == "3_completed"

    epic_events, _ = read_events("epic_001", 0, root=root)
    completed = [event for event in epic_events if event.type == "FeatureCompleted"]
    assert len(completed) == 1
    assert completed[0].payload == {"feature_id": "feat_001"}
    assert completed[0].dest == "epic_001"


def test_open_human_comment_blocks_completion(tmp_path: Path) -> None:
    root = _rollup_board(tmp_path)
    write_closeout("feat_001", "Ready pending review.", root=root)
    comment("feat_001", "Scope", "wait", author="human", root=root)

    assert try_complete_feature("feat_001", root=root) is False

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "active"
    assert feature.meta.path.parent.name == "2_active"
    epic_events, _ = read_events("epic_001", 0, root=root)
    assert not any(event.type == "FeatureCompleted" for event in epic_events)


def test_resolved_human_comment_does_not_block(tmp_path: Path) -> None:
    root = _rollup_board(tmp_path)
    write_closeout("feat_001", "Shipped.", root=root)
    cmt_id = comment("feat_001", "Scope", "question", author="human", root=root)
    resolve_comment("feat_001", cmt_id, root=root)

    assert try_complete_feature("feat_001", root=root) is True


def test_missing_closeout_is_synthesized_after_all_children_complete(tmp_path: Path) -> None:
    root = _rollup_board(tmp_path)

    assert try_complete_feature("feat_001", root=root) is True

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "completed"
    assert "## Closeout" in feature.body
    assert "`task_001` (Task one)" in feature.body
    assert "`task_002` (Task two)" in feature.body


def test_partial_task_completion_blocks(tmp_path: Path) -> None:
    root = _rollup_board(tmp_path)
    write_closeout("feat_001", "Almost there.", root=root)
    from cascade.board.store import move_doc

    move_doc("task_002", "active", root=root)

    assert try_complete_feature("feat_001", root=root) is False
    assert read_doc("feat_001", root=root).meta.status == "active"


def test_child_task_via_parent_only_not_in_children_list(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=[],
    )
    add_doc(
        root,
        id="task_001",
        title="Only task",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    write_closeout("feat_001", "Single task feature complete.", root=root)

    assert try_complete_feature("feat_001", root=root) is True


def test_on_task_merged_synthesizes_closeout_without_model_action(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Last task",
        tier="task",
        status="completed",
        parent="feat_001",
    )

    on_task_merged("task_001", root=root)

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "completed"
    assert feature.meta.path.parent.name == "3_completed"
    assert "Completed child work: `task_001` (Last task)." in feature.body
    epic_events, _ = read_events("epic_001", 0, root=root)
    assert any(event.type == "FeatureCompleted" for event in epic_events)


def test_on_task_merged_completes_when_gates_hold(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Last task",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    write_closeout("feat_001", "Merged the final task.", root=root)

    on_task_merged("task_001", root=root)

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "completed"
    epic_events, _ = read_events("epic_001", 0, root=root)
    assert any(event.type == "FeatureCompleted" for event in epic_events)


def test_write_closeout_replaces_existing_paragraph(tmp_path: Path) -> None:
    root = _rollup_board(tmp_path)
    write_closeout("feat_001", "First version.", root=root)
    write_closeout("feat_001", "Final version.", root=root)

    feature = read_doc("feat_001", root=root)
    assert "## Closeout" in feature.body
    assert "First version." not in feature.body
    assert "Final version." in feature.body
    assert feature.meta.path.parent.name == "2_active"


def test_write_closeout_preserves_later_sections(tmp_path: Path) -> None:
    root = _rollup_board(tmp_path)
    from cascade.board.store import write_doc

    doc = read_doc("feat_001", root=root)
    doc.body = (
        doc.body.rstrip()
        + "\n\n## Closeout\n\nOriginal closeout.\n\n## Follow-up\n\nKeep this section.\n"
    )
    write_doc(doc, root=root)

    write_closeout("feat_001", "Updated closeout.", root=root)

    feature = read_doc("feat_001", root=root)
    assert "Updated closeout." in feature.body
    assert "Original closeout." not in feature.body
    assert "## Follow-up" in feature.body
    assert "Keep this section." in feature.body
