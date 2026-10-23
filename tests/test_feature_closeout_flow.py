from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import cascade.review as review_module
from cascade.approvals import approve_epic_plan
from cascade.automation import advance_work
from cascade.board.store import read_doc
from cascade.boss.rollup import on_task_merged, try_complete_feature
from cascade.review import ensure_feature_review
from cascade.tracking import MergeRequest
from cascade.watchdog.events import read_events
from tests.support import add_doc, make_repo


def _completed_feature_board(root: Path, *, sibling: bool = False) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="First feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Finished task",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    if sibling:
        add_doc(
            root,
            id="feat_002",
            title="Next feature",
            tier="feature",
            parent="epic_001",
            depends_on=["feat_001"],
        )


def test_final_task_merge_synthesizes_closeout_and_opens_review(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _completed_feature_board(root)
    opened: list[str] = []
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    def _open_review(feature_id: str, *, root: Path):
        opened.append(feature_id)
        state_path = root / ".cascade" / "reviews.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    feature_id: {
                        "url": f"https://github.example/o/r/pull/{feature_id}",
                        "number": "1",
                        "forge": "github",
                        "source_branch": "feat/feat_001",
                        "target_branch": "epic/epic_001",
                        "draft": False,
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return None

    monkeypatch.setattr("cascade.review.ensure_feature_review", _open_review)

    on_task_merged("task_001", root=root)

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "completed"
    assert feature.meta.path.parent.name == "3_completed"
    assert "Completed child work: `task_001` (Finished task)." in feature.body
    assert opened == ["feat_001"]


def test_review_open_toast_is_linked_idempotent_and_restart_safe(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _completed_feature_board(root)
    mr = MergeRequest(
        url="https://github.example/o/r/pull/17",
        number="17",
        forge="github",
        source_branch="feature/feat_001",
        target_branch="epic/epic_001",
        draft=False,
    )
    monkeypatch.setattr("cascade.review.locate_trunk", lambda value: Path(value))
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    monkeypatch.setattr(
        "cascade.review.get_integration_worktree",
        lambda _root, _tier, _id: SimpleNamespace(path=root),
    )
    publication_order: list[str] = []
    monkeypatch.setattr(
        "cascade.review.push_branch", lambda *_args: publication_order.append("push")
    )
    monkeypatch.setattr(
        "cascade.feature.publication.prepare_feature_publication",
        lambda *_args, **_kwargs: publication_order.append("prepare"),
    )
    from cascade.boss.rollup import write_closeout

    write_closeout("feat_001", "Done.", root=root)
    create_kwargs: list[dict[str, object]] = []

    def create(*_args, **kwargs) -> MergeRequest:
        publication_order.append("create")
        create_kwargs.append(kwargs)
        return mr

    monkeypatch.setattr("cascade.review.create_merge_request", create)

    assert ensure_feature_review("feat_001", root=root) == mr
    from cascade.board.store import move_doc

    move_doc("feat_001", "completed", root=root)
    assert ensure_feature_review("feat_001", root=root).url == mr.url
    assert create_kwargs == [
        {
            "title": "feat_001: First feature",
            "body": (
                "Implements `feat_001` for `epic_001`. This review is managed by "
                "Cascade; review comments are delivered to the Feature Team."
            ),
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "draft": False,
        }
    ]
    assert publication_order[:4] == ["prepare", "push", "push", "create"]

    events, _ = read_events("war_room", 0, root=root)
    opened = [event for event in events if event.payload.get("kind") == "feature_review_opened"]
    assert len(opened) == 1
    assert opened[0].payload["url"] == mr.url
    state = json.loads((root / ".cascade" / "reviews.json").read_text(encoding="utf-8"))
    assert state["feat_001"]["toast_notified"] is True


def test_saved_review_retries_linked_toast_after_append_failure(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _completed_feature_board(root)
    mr = MergeRequest(
        url="https://github.example/o/r/pull/18",
        number="18",
        forge="github",
        source_branch="feat/feat_001",
        target_branch="epic/epic_001",
        draft=False,
    )
    creates: list[str] = []
    monkeypatch.setattr("cascade.review.locate_trunk", lambda value: Path(value))
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    monkeypatch.setattr(
        "cascade.review.get_integration_worktree",
        lambda _root, _tier, _id: SimpleNamespace(path=root),
    )
    monkeypatch.setattr("cascade.review.push_branch", lambda *_args: None)
    monkeypatch.setattr(
        "cascade.feature.publication.prepare_feature_publication",
        lambda *_args, **_kwargs: None,
    )
    from cascade.boss.rollup import write_closeout

    write_closeout("feat_001", "Done.", root=root)

    def create(*_args, **_kwargs) -> MergeRequest:
        creates.append("created")
        return mr

    monkeypatch.setattr("cascade.review.create_merge_request", create)
    real_append = review_module.append_event
    monkeypatch.setattr(
        "cascade.review.append_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("queue unavailable")),
    )

    with pytest.raises(OSError, match="queue unavailable"):
        ensure_feature_review("feat_001", root=root)

    state_path = root / ".cascade" / "reviews.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["feat_001"]["toast_notified"] is False
    monkeypatch.setattr("cascade.review.append_event", real_append)

    recovered = ensure_feature_review("feat_001", root=root)

    assert recovered is not None and recovered.url == mr.url
    assert creates == ["created"]
    events, _ = read_events("war_room", 0, root=root)
    assert len(events) == 1
    assert events[0].payload["url"] == mr.url
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["feat_001"]["toast_notified"] is True


def test_merged_review_releases_next_dependent_feature_on_next_pass(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text("[automation]\nenabled = true\n", encoding="utf-8")
    _completed_feature_board(root, sibling=True)
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    def _ensure(feature_id: str, *, root: Path):
        state_path = root / ".cascade" / "reviews.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    feature_id: {
                        "url": f"https://github.example/o/r/pull/{feature_id}",
                        "number": "1",
                        "forge": "github",
                        "source_branch": "feat/feat_001",
                        "target_branch": "epic/epic_001",
                        "draft": False,
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return None

    monkeypatch.setattr("cascade.review.ensure_feature_review", _ensure)
    from cascade.boss.rollup import write_closeout

    write_closeout("feat_001", "Done.", root=root)
    review_pending = True
    monkeypatch.setattr(
        "cascade.review.feature_review_pending",
        lambda feature_id, *, root: review_pending and feature_id == "feat_001",
    )
    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args: None)
    approve_epic_plan("epic_001", root=root)

    first = advance_work(root)
    assert first["features"] == []
    assert read_doc("feat_001", root=root).meta.status == "completed"
    assert read_doc("feat_002", root=root).meta.status == "backlog"

    assert try_complete_feature("feat_001", root=root, review_merged=True) is True
    review_pending = False
    second = advance_work(root)

    assert second["features"] == ["feat_002"]
    assert read_doc("feat_001", root=root).meta.status == "completed"
    assert read_doc("feat_002", root=root).meta.status == "active"


def test_polling_merged_review_does_not_create_source_completion_commit(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _completed_feature_board(root)
    state_path = root / ".cascade" / "reviews.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "feat_001": {
                    "url": "https://github.example/o/r/pull/19",
                    "number": "19",
                    "forge": "github",
                    "source_branch": "feat/feat_001",
                    "target_branch": "epic/epic_001",
                    "draft": False,
                    "seen_comments": [],
                    "toast_notified": True,
                }
            }
        ),
        encoding="utf-8",
    )
    from cascade.board.store import move_doc

    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    move_doc("feat_001", "completed", root=root)
    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda *_args, **_kwargs: {"state": "merged", "comments": []},
    )
    synced: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        "cascade.review.get_integration_worktree",
        lambda *_args, **_kwargs: SimpleNamespace(path=root),
    )
    monkeypatch.setattr(
        "cascade.review.fast_forward_branch",
        lambda path, branch: synced.append((path, branch)) or "merged-sha",
    )
    monkeypatch.setattr("cascade.review.push_branch", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "cascade.boss.rollup.move_doc",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("post-merge move")),
    )

    review_module.poll_feature_reviews(root)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["feat_001"]["closed"] is True
    assert synced == [(root, "epic/epic_001")]
    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "completed"


def test_merged_review_closes_active_feature_copy_on_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _completed_feature_board(root)
    state_path = root / ".cascade" / "reviews.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "feat_001": {
            "url": "https://github.example/o/r/pull/20",
            "number": "20",
            "forge": "github",
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "draft": False,
            "seen_comments": [],
            "toast_notified": True,
        }
    }), encoding="utf-8")
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda *_args, **_kwargs: {"state": "merged", "comments": []},
    )
    monkeypatch.setattr(
        "cascade.review.get_integration_worktree",
        lambda *_args, **_kwargs: SimpleNamespace(path=root),
    )
    monkeypatch.setattr("cascade.review.fast_forward_branch", lambda *_args: "merged-sha")
    pushes: list[str] = []

    def push_target(_root: Path, branch: str) -> None:
        pushes.append(branch)
        if len(pushes) == 1:
            from cascade.board.errors import GitError

            raise GitError("temporary push failure")

    monkeypatch.setattr("cascade.review.push_branch", push_target)

    assert read_doc("feat_001", root=root).meta.status == "active"
    review_module.poll_feature_reviews(root)
    assert read_doc("feat_001", root=root).meta.status == "completed"
    assert json.loads(state_path.read_text(encoding="utf-8"))["feat_001"].get("closed") is None
    events, _ = read_events("epic_001", 0, root=root)
    assert not any(event.type == "FeatureCompleted" for event in events)
    review_module.poll_feature_reviews(root)
    review_module.poll_feature_reviews(root)

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "completed"
    assert feature.meta.path.parent.name == "3_completed"
    assert json.loads(state_path.read_text(encoding="utf-8"))["feat_001"]["closed"] is True
    events, _ = read_events("epic_001", 0, root=root)
    assert len([event for event in events if event.type == "FeatureCompleted"]) == 1
    assert pushes == ["epic/epic_001", "epic/epic_001"]
