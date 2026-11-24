"""Immutable Feature review generations and stale-callback fencing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import cascade.review as review
import pytest
from cascade.tracking import MergeRequest
from tests.support import add_doc, make_repo


def _projection(url: str, *, closed: bool = False) -> dict[str, object]:
    return {
        "url": url,
        "number": url.rsplit("/", 1)[-1],
        "forge": "github",
        "source_branch": "feat/feat_001",
        "target_branch": "epic/epic_001",
        "source_head": "source-head",
        "target_head": "target-head",
        "draft": False,
        "closed": closed,
        "seen_comments": [],
        "toast_notified": True,
    }


def test_new_review_generation_preserves_accepted_history(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    review._update_record(
        root,
        "feat_001",
        _projection("https://example.test/pulls/1"),
        create=True,
    )
    review._update_record(
        root,
        "feat_001",
        {
            "closed": True,
            "accepted_merge_sha": "merge-zero",
            "accepted_source_head": "source-head",
            "accepted_target_head": "target-head",
            "reconciliation_status": "accepted",
        },
    )
    old_callback = review.review_record_for_feature("feat_001", root=root)
    assert old_callback is not None

    current = review._store_review_generation(
        root,
        "feat_001",
        _projection("https://example.test/pulls/2"),
        generation=1,
        action_id="feature_repair:feat_001:one",
    )

    assert current["schema_version"] == 2
    assert current["current_generation"] == 1
    assert current["url"] == "https://example.test/pulls/2"
    historical = review.feature_review_generation("feat_001", 0, root=root)
    assert historical is not None
    assert historical["accepted_merge_sha"] == "merge-zero"
    assert historical["reconciliation_status"] == "accepted"
    assert not review.review_callback_is_current("feat_001", old_callback, root=root)
    assert review.review_callback_is_current("feat_001", current, root=root)
    assert not review.review_callback_is_current(
        "feat_001",
        current,
        root=root,
        snapshot={"merge_sha": "merge-one", "source_revision": "old-source"},
    )
    assert review.review_callback_is_current(
        "feat_001",
        current,
        root=root,
        snapshot={"merge_sha": "merge-one", "source_revision": "source-head"},
    )


def test_legacy_closed_record_is_generation_zero_without_inferred_heads(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    legacy = _projection("https://example.test/pulls/7", closed=True)
    review._update_record(root, "feat_001", legacy, create=True)
    versioned = review._store_review_generation(
        root, "feat_001", legacy, generation=0, action_id=None
    )

    generation = review.feature_review_generation("feat_001", 0, root=root)
    assert generation is not None
    assert versioned["current_generation"] == 0
    assert generation.get("accepted_merge_sha") is None
    assert generation["reconciliation_status"] == "legacy_unverified"


def test_generation_save_failure_replays_without_overwriting_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    review._store_review_generation(
        root,
        "feat_001",
        _projection("https://example.test/pulls/1"),
        generation=0,
        action_id=None,
    )
    review._update_record(
        root,
        "feat_001",
        {
            "closed": True,
            "accepted_merge_sha": "merge-zero",
            "accepted_source_head": "source-head",
            "accepted_target_head": "target-head",
            "reconciliation_status": "accepted",
        },
    )
    before = (root / ".cascade/reviews.json").read_bytes()
    real_save = review._save
    failed = False

    def fail_once(save_root, state):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("injected review save failure")
        return real_save(save_root, state)

    monkeypatch.setattr(review, "_save", fail_once)
    with pytest.raises(OSError, match="injected"):
        review._store_review_generation(
            root,
            "feat_001",
            _projection("https://example.test/pulls/2"),
            generation=1,
            action_id="feature_repair:feat_001:one",
        )
    assert (root / ".cascade/reviews.json").read_bytes() == before

    review._store_review_generation(
        root,
        "feat_001",
        _projection("https://example.test/pulls/2"),
        generation=1,
        action_id="feature_repair:feat_001:one",
    )
    historical = review.feature_review_generation("feat_001", 0, root=root)
    assert historical is not None
    assert historical["accepted_merge_sha"] == "merge-zero"


def _repair_publication_board(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root, id="feat_001", title="Feature", tier="feature",
        status="completed", parent="epic_001",
    )
    monkeypatch.setattr(review, "locate_trunk", lambda value: Path(value))
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)
    monkeypatch.setattr(
        review, "get_integration_worktree",
        lambda _root, _tier, _id: SimpleNamespace(path=root),
    )
    monkeypatch.setattr("cascade.stacked_dispatch.review_target_branch", lambda *_a, **_k: "epic/epic_001")
    monkeypatch.setattr("cascade.feature.publication.prepare_feature_publication", lambda *_a, **_k: SimpleNamespace(remote_lease_sha=None))
    monkeypatch.setattr(review, "push_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "cascade.feature.repair.current_feature_repair_record",
        lambda *_a, **_k: {"generation": 1, "action_id": "feature_repair:feat_001:one"},
    )


def test_open_historical_review_is_refreshed_for_repair_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _repair_publication_board(root, monkeypatch)
    old = _projection("https://example.test/pulls/1")
    review._store_review_generation(root, "feat_001", old, generation=0, action_id=None)
    mr = review._record_to_mr(old)
    monkeypatch.setattr(
        review, "merge_request_snapshot",
        lambda *_a, **_k: {
            "state": "open", "url": mr.url,
            "source_branch": "feat/feat_001", "target_branch": "epic/epic_001",
            "source_revision": "old-source",
        },
    )
    monkeypatch.setattr(review, "find_merge_request", lambda *_a, **_k: None)
    monkeypatch.setattr(
        review, "create_merge_request",
        lambda *_a, **_k: pytest.fail("open review must be reused"),
    )

    refreshed = review.ensure_feature_review("feat_001", root=root)

    assert refreshed is not None and refreshed.url == mr.url
    current = review.review_record_for_feature("feat_001", root=root)
    assert current["current_generation"] == 1
    assert current["route"] == "refresh"
    assert current["previous_review_url"] == mr.url
    assert review.feature_review_generation("feat_001", 0, root=root)["url"] == mr.url


def test_merged_historical_review_creates_linked_follow_up_and_fences_old_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _repair_publication_board(root, monkeypatch)
    old = _projection("https://example.test/pulls/1")
    old_record = review._store_review_generation(
        root, "feat_001", old, generation=0, action_id=None
    )
    old_mr = review._record_to_mr(old)
    monkeypatch.setattr(
        review, "merge_request_snapshot",
        lambda *_a, **_k: {
            "state": "merged", "url": old_mr.url,
            "source_branch": "feat/feat_001", "target_branch": "epic/epic_001",
            "source_revision": "source-head",
            "merge_sha": "merge-zero",
        },
    )
    follow_up = MergeRequest(
        url="https://example.test/pulls/2", number="2", forge="github",
        source_branch="feat/feat_001", target_branch="epic/epic_001", draft=False,
    )
    monkeypatch.setattr(review, "find_merge_request", lambda *_a, **_k: None)
    monkeypatch.setattr(review, "create_merge_request", lambda *_a, **_k: follow_up)

    published = review.ensure_feature_review("feat_001", root=root)

    assert published == follow_up
    current = review.review_record_for_feature("feat_001", root=root)
    assert current["route"] == "follow_up"
    assert current["previous_review_url"] == old_mr.url
    assert current["url"] == follow_up.url
    assert review.feature_review_generation("feat_001", 0, root=root)["url"] == old_mr.url
    assert not review.review_callback_is_current("feat_001", old_record, root=root)


def test_follow_up_save_failure_recovers_same_remote_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _repair_publication_board(root, monkeypatch)
    old = _projection("https://example.test/pulls/1")
    review._store_review_generation(root, "feat_001", old, generation=0, action_id=None)
    monkeypatch.setattr(
        review, "merge_request_snapshot",
        lambda *_a, **_k: {
            "state": "merged", "url": old["url"],
            "source_branch": "feat/feat_001", "target_branch": "epic/epic_001",
            "source_revision": "source-head", "merge_sha": "merge-zero",
        },
    )
    follow_up = MergeRequest(
        url="https://example.test/pulls/2", number="2", forge="github",
        source_branch="feat/feat_001", target_branch="epic/epic_001", draft=False,
    )
    created: list[MergeRequest] = []
    monkeypatch.setattr(
        review, "create_merge_request",
        lambda *_a, **_k: created.append(follow_up) or follow_up,
    )
    monkeypatch.setattr(
        review, "find_merge_request",
        lambda *_a, **_k: created[0] if created else None,
    )
    real_save = review._save
    failed = False

    def fail_generation_once(save_root, state):
        nonlocal failed
        if not failed and state["feat_001"].get("current_generation") == 1:
            failed = True
            raise OSError("injected generation save failure")
        return real_save(save_root, state)

    monkeypatch.setattr(review, "_save", fail_generation_once)
    with pytest.raises(OSError, match="injected generation save failure"):
        review.ensure_feature_review("feat_001", root=root)

    recovered = review.ensure_feature_review("feat_001", root=root)
    assert recovered == follow_up
    assert created == [follow_up]
    assert review.review_record_for_feature("feat_001", root=root)["current_generation"] == 1
