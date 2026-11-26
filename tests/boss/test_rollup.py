"""Feature rollup and closeout (task_041)."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cascade.review as review
from cascade.board.store import move_doc, read_doc, write_doc
from cascade.boss.rollup import (
    current_feature_obligation,
    on_task_merged,
    try_complete_feature,
    write_closeout,
)
from cascade.comments.store import comment, resolve_comment
from cascade.feature.mint import mint_task
from cascade.feature.repair import (
    admit_feature_repair,
    mark_feature_repair_delivery_pending,
)
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.types import Event
from tests.support import add_doc, commit_board, make_repo


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


def _reviewed_completed_feature(tmp_path: Path) -> tuple[Path, str, str]:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    commit_board(root, "target base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "branch", "epic/epic_001", base], cwd=root, check=True)
    (root / "delivery.txt").write_text("accepted delivery\n", encoding="utf-8")
    commit_board(root, "accepted delivery")
    accepted = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "branch", "feat/feat_001", accepted], cwd=root, check=True
    )
    return root, base, accepted


def _store_review(
    root: Path,
    *,
    base: str,
    source: str,
    generation: int = 0,
    accepted: bool = False,
) -> None:
    review._store_review_generation(
        root,
        "feat_001",
        {
            "url": "https://example.test/pulls/1",
            "number": "1",
            "forge": "github",
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_head": source,
            "target_head": base,
            "draft": False,
            "closed": accepted,
        },
        generation=generation,
        action_id=None if generation == 0 else f"repair:{generation}",
    )
    if accepted:
        review._update_record(
            root,
            "feat_001",
            {
                "accepted_merge_sha": source,
                "accepted_source_head": source,
                "accepted_target_head": base,
                "reconciliation_status": "accepted",
            },
        )


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
    resolve_comment("feat_001", cmt_id, author="human", root=root)

    assert try_complete_feature("feat_001", root=root) is True


def test_missing_closeout_is_synthesized_after_all_children_complete(
    tmp_path: Path,
) -> None:
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


def test_current_repair_generation_fences_old_review_callback(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    feature = read_doc("feat_001", root=root)
    feature.meta.approved_at = datetime.now(timezone.utc)
    write_doc(feature, root=root)
    commit_board(root)
    admit_feature_repair("feat_001", "mint:late", root=root)

    assert not current_feature_obligation("feat_001", root=root).satisfied
    task_id = mint_task(
        "Late repair",
        feature_id="feat_001",
        repair_request_id="mint:late",
        root=root,
    )
    move_doc(task_id, "completed", root=root)
    append_event(
        "feat_001",
        Event(
            type="TaskMerged",
            ts=datetime.now(timezone.utc),
            payload={
                "task_id": task_id,
                "feature_id": "feat_001",
                "merge_sha": "delivery",
            },
            dest="feat_001",
        ),
        root=root,
    )
    review._store_review_generation(
        root,
        "feat_001",
        {
            "url": "https://example.test/pulls/2",
            "number": "2",
            "forge": "github",
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_head": "source",
            "target_head": "target",
            "draft": False,
            "closed": False,
        },
        generation=1,
        action_id="feature_repair:feat_001:late",
    )
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)

    assert not current_feature_obligation(
        "feat_001", root=root, review_generation=0
    ).satisfied
    assert not current_feature_obligation(
        "feat_001", root=root, review_generation=1
    ).satisfied


def test_completed_open_original_review_retains_closeout_and_owner(
    tmp_path: Path, monkeypatch
) -> None:
    root, base, accepted = _reviewed_completed_feature(tmp_path)
    _store_review(root, base=base, source=accepted)
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)

    assert try_complete_feature("feat_001", root=root, review_merged=True) is False
    assert _feature_completed_events(root) == []
    assert review.review_record_for_feature("feat_001", root=root)["url"] == (
        "https://example.test/pulls/1"
    )
    assert subprocess.run(
        ["git", "show-ref", "--verify", "refs/heads/feat/feat_001"],
        cwd=root,
        check=False,
        capture_output=True,
    ).returncode == 0


def test_closeout_requires_exact_acceptance_and_intended_target_then_emits_once(
    tmp_path: Path, monkeypatch
) -> None:
    root, base, accepted = _reviewed_completed_feature(tmp_path)
    _store_review(root, base=base, source=accepted, generation=1, accepted=True)
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)

    # Exact forge acceptance is still pending until the accepted merge is an
    # ancestor of the intended Epic branch.
    assert try_complete_feature("feat_001", root=root, review_merged=True) is False
    assert _feature_completed_events(root) == []

    subprocess.run(
        ["git", "branch", "-f", "epic/epic_001", accepted], cwd=root, check=True
    )
    assert try_complete_feature("feat_001", root=root, review_merged=True) is True
    assert try_complete_feature("feat_001", root=root, review_merged=True) is True
    assert len(_feature_completed_events(root)) == 1


def _feature_completed_events(root: Path) -> list[Event]:
    events, _ = read_events("epic_001", 0, root=root)
    return [event for event in events if event.type == "FeatureCompleted"]


def test_original_repair_task_is_the_current_closeout_child(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
        children=["task_001"],
    )
    feature = read_doc("feat_001", root=root)
    feature.meta.approved_at = datetime.now(timezone.utc)
    write_doc(feature, root=root)
    add_doc(
        root,
        id="task_001",
        title="Original task",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    commit_board(root)
    admit_feature_repair(
        "feat_001", "task_001:queued_merge", task_id="task_001", root=root
    )
    mark_feature_repair_delivery_pending(
        "task_001",
        {
            "task_id": "task_001",
            "deliverable_sha": "source",
            "feature_base_sha": "target",
        },
        root=root,
    )
    append_event(
        "feat_001",
        Event(
            type="TaskMerged",
            ts=datetime.now(timezone.utc),
            payload={"task_id": "task_001", "merge_sha": "delivery"},
            dest="feat_001",
        ),
        root=root,
    )

    obligation = current_feature_obligation("feat_001", root=root)
    assert obligation.generation == 1
    assert obligation.reason == "local integration evidence is missing"


def test_on_task_merged_synthesizes_closeout_without_model_action(
    tmp_path: Path,
) -> None:
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
