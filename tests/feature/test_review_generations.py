"""Immutable Feature review generations and stale-callback fencing."""

from __future__ import annotations

from pathlib import Path

import cascade.review as review
import pytest
from tests.support import make_repo


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
