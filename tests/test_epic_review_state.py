"""Typed persistence for the epic implementation-review close stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.review import (
    EpicCloseBlocker,
    EpicReviewSnapshot,
    epic_review_snapshot,
    persist_epic_review_snapshot,
)
from tests.support import make_repo


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
