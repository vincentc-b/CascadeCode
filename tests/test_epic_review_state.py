"""Typed persistence for the epic implementation-review close stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.board.errors import GitError, NotFound
from cascade.board.store import list_board, read_doc
from cascade.review import (
    EpicCloseBlocker,
    EpicReviewSnapshot,
    epic_review_snapshot,
    persist_epic_review_snapshot,
    refresh_epic_review_snapshot,
)
from cascade.tracking import ReviewNotFound
from cascade.war_room.serialize import board_view_from_index, work_doc_to_dict
from tests.support import add_doc, make_repo


def test_epic_review_snapshot_round_trips_all_close_fields(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    snapshot = EpicReviewSnapshot(
        stage="implementation_review_pending",
        review_url="https://github.example/acme/project/pull/17",
        source_branch="epic/epic_001",
        target_branch="main",
        forge_state="open",
    )

    persist_epic_review_snapshot("epic_001", snapshot, root=root)

    assert epic_review_snapshot("epic_001", root=root) == snapshot
    record = json.loads((root / ".cascade" / "reviews.json").read_text())["epic_001"]
    assert record["kind"] == "epic_close"
    assert record["review_url"] == snapshot.review_url


def test_epic_review_snapshot_loads_legacy_merge_request_record(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    path = root / ".cascade" / "reviews.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"epic_001": {
        "url": "https://gitlab.example/acme/project/-/merge_requests/3",
        "source_branch": "epic/epic_001",
        "target_branch": "main",
        "closed": False,
    }}), encoding="utf-8")

    loaded = epic_review_snapshot("epic_001", root=root)

    assert loaded is not None
    assert loaded.stage == "implementation_review_pending"
    assert loaded.forge_state == "open"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "/pull/1", "https://u:p@example/pull/1"])
def test_epic_review_snapshot_rejects_unsafe_review_urls(url: str) -> None:
    with pytest.raises(ValueError, match="review URL"):
        EpicReviewSnapshot(
            stage="implementation_review_pending",
            review_url=url,
            source_branch="epic/epic_001",
            target_branch="main",
            forge_state="open",
        )


def test_blocked_snapshot_requires_structured_actionable_details() -> None:
    with pytest.raises(ValueError, match="actionable blocker"):
        EpicReviewSnapshot(stage="blocked")

    snapshot = EpicReviewSnapshot(
        stage="blocked",
        forge_state="unknown",
        blocker=EpicCloseBlocker(
            code="review_lookup_failed",
            message="Retry after restoring forge connectivity.",
            retryable=True,
        ),
    )
    assert snapshot.blocker is not None and snapshot.blocker.retryable


@pytest.mark.parametrize(
    "snapshot",
    [
        EpicReviewSnapshot(
            stage="implementation_review_pending",
            review_url="https://github.example/acme/project/pull/17",
            source_branch="epic/epic_001",
            target_branch="main",
            forge_state="open",
        ),
        EpicReviewSnapshot(
            stage="blocked",
            review_url="https://github.example/acme/project/pull/17",
            source_branch="epic/epic_001",
            target_branch="main",
            forge_state="unknown",
            blocker=EpicCloseBlocker(
                code="review_lookup_failed",
                message="Retry after restoring forge connectivity.",
                retryable=True,
            ),
        ),
    ],
)
def test_board_and_doc_serialize_the_same_epic_review_state(
    tmp_path: Path, snapshot: EpicReviewSnapshot
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Root epic", tier="epic")
    persist_epic_review_snapshot("epic_001", snapshot, root=root)

    board = board_view_from_index(list_board(root), root=root)
    doc = work_doc_to_dict(read_doc("epic_001", root=root), root=root)

    board_state = board["epics"]["1_backlog"][0]["implementation_review"]
    assert board_state == doc["meta"]["implementation_review"]
    assert board_state == {
        "close_stage": snapshot.stage,
        "review_url": snapshot.review_url,
        "source_branch": snapshot.source_branch,
        "target_branch": snapshot.target_branch,
        "forge_state": snapshot.forge_state,
        "blocker": (
            {
                "code": snapshot.blocker.code,
                "message": snapshot.blocker.message,
                "retryable": snapshot.blocker.retryable,
            }
            if snapshot.blocker
            else None
        ),
    }


@pytest.mark.parametrize("stage", ["implementation_review_pending", "blocked"])
def test_epic_with_unresolved_close_review_stays_in_active_board_column(
    tmp_path: Path, stage: str
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="completed")
    blocker = (
        EpicCloseBlocker(code="review_lookup_failed", message="Retry review lookup.", retryable=True)
        if stage == "blocked"
        else None
    )
    persist_epic_review_snapshot(
        "epic_001",
        EpicReviewSnapshot(
            stage=stage,
            review_url="https://github.example/acme/project/pull/17",
            source_branch="epic/epic_001",
            target_branch="main",
            forge_state="open" if blocker is None else "unknown",
            blocker=blocker,
        ),
        root=root,
    )

    board = board_view_from_index(list_board(root), root=root)

    assert [row["id"] for row in board["epics"]["2_active"]] == ["epic_001"]
    assert board["epics"]["3_completed"] == []
    assert board["epics"]["2_active"][0]["implementation_review"]["close_stage"] == stage


def test_epic_moves_to_completed_column_after_review_close_reconciles(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="completed")
    persist_epic_review_snapshot(
        "epic_001",
        EpicReviewSnapshot(stage="completed", forge_state="merged"),
        root=root,
    )

    board = board_view_from_index(list_board(root), root=root)

    assert board["epics"]["2_active"] == []
    assert [row["id"] for row in board["epics"]["3_completed"]] == ["epic_001"]


def test_refresh_reconstructs_pending_review_and_persists_forge_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    original = EpicReviewSnapshot(
        stage="blocked",
        review_url="https://github.com/acme/project/pull/17",
        source_branch="epic/epic_001",
        target_branch="main",
        blocker=EpicCloseBlocker(
            code="review_lookup_failed", message="Retry forge lookup.", retryable=True
        ),
    )
    persist_epic_review_snapshot("epic_001", original, root=root)
    monkeypatch.setattr("cascade.review.detect_forge", lambda _root: "github")
    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda _root, review: {"state": "OPEN", "url": review.url},
    )

    refreshed = refresh_epic_review_snapshot("epic_001", root=root)

    assert refreshed == EpicReviewSnapshot(
        stage="implementation_review_pending",
        review_url=original.review_url,
        source_branch=original.source_branch,
        target_branch=original.target_branch,
        forge_state="open",
    )
    assert epic_review_snapshot("epic_001", root=root) == refreshed

    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda _root, review: {"state": "merged", "url": review.url},
    )
    merged = refresh_epic_review_snapshot("epic_001", root=root)
    assert merged is not None
    assert merged.stage == "implementation_review_pending"
    assert merged.forge_state == "merged"


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (ReviewNotFound("gone"), "review_missing", False),
        (NotFound("gone"), "review_missing", False),
        (GitError("offline"), "review_lookup_failed", True),
    ],
)
def test_refresh_persists_actionable_lookup_blocker_without_replacing_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    code: str,
    retryable: bool,
) -> None:
    root = make_repo(tmp_path)
    original = EpicReviewSnapshot(
        stage="implementation_review_pending",
        review_url="https://github.com/acme/project/pull/17",
        source_branch="epic/epic_001",
        target_branch="main",
        forge_state="open",
    )
    persist_epic_review_snapshot("epic_001", original, root=root)
    monkeypatch.setattr("cascade.review.detect_forge", lambda _root: "github")

    def fail_lookup(_root: Path, _review: object) -> dict[str, object]:
        raise error

    monkeypatch.setattr("cascade.review.merge_request_snapshot", fail_lookup)

    refreshed = refresh_epic_review_snapshot("epic_001", root=root)

    assert refreshed is not None and refreshed.stage == "blocked"
    assert refreshed.review_url == original.review_url
    assert refreshed.source_branch == original.source_branch
    assert refreshed.target_branch == original.target_branch
    assert refreshed.blocker is not None
    assert (refreshed.blocker.code, refreshed.blocker.retryable) == (code, retryable)
