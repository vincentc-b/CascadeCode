"""Immutable Feature review generations and stale-callback fencing."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import cascade.review as review
import pytest
from cascade.board.store import read_doc, write_doc
from cascade.board.types import CancellationFeedback
from cascade.tracking import MergeRequest
from cascade.review_validation import (
    ExactValidationMaterial,
    exact_material_fingerprint,
)
from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event
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


def test_exact_candidate_receipt_is_shared_by_acceptance_and_fenced_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    source_sha, target_sha = "a" * 40, "b" * 40
    merge_sha, observed_target = "c" * 40, "d" * 40
    current = _projection("https://example.test/pulls/12")
    current.update(source_head=source_sha, target_head=target_sha)
    current = review._store_review_generation(
        root,
        "feat_001",
        current,
        generation=2,
        action_id="feature_repair:feat_001:two",
    )
    identity = {
        "candidate": {
            "source_sha": source_sha,
            "target_sha": target_sha,
            "result_commit": "e" * 40,
            "result_tree": "f" * 40,
        },
        "review": {
            "action_id": "review:12",
            "review_id": "12",
            "review_url": current["url"],
            "source_ref": current["source_branch"],
            "target_ref": current["target_branch"],
            "generation": "review-generation-12",
        },
        "profile": {"id": "approved"},
        "runtime": {"python": "3.12"},
    }
    material = ExactValidationMaterial(identity, exact_material_fingerprint(identity))
    receipt = {
        "state": "settled",
        "operation_id": "validator:12",
        "exact_validation_material": identity,
        "material_fingerprint": material.fingerprint,
        "observation": {"outcome": "success", "validation_status": "passed"},
    }
    monkeypatch.setattr(
        "cascade.review_validation.match_review_validation_receipt",
        lambda incident_id, candidate, **_kwargs: (
            (
                "matching_green",
                receipt,
            )
            if incident_id == "review:12" and candidate == material
            else ("admission_required", None)
        ),
    )
    assert review.record_exact_candidate_proof(
        "feat_001", "review:12", "validator:12", material, root=root
    )
    current = review.review_record_for_feature("feat_001", root=root)
    assert current is not None
    snapshot = {
        "state": "merged",
        "url": current["url"],
        "source_branch": current["source_branch"],
        "target_branch": current["target_branch"],
        "source_revision": source_sha,
        "target_revision": observed_target,
        "merge_sha": merge_sha,
        "post_merge_ci": {
            "state": "green",
            "merge_sha": merge_sha,
            "observed_target_sha": observed_target,
        },
    }

    assert review._accept_current_review_generation(
        "feat_001", current, snapshot, root=root
    )
    accepted = review.review_record_for_feature("feat_001", root=root)
    assert accepted is not None
    assert accepted["accepted_merge_identity"]["merge_sha"] == merge_sha
    assert accepted["accepted_merge_identity"]["review_generation"] == 2
    assert accepted["accepted_candidate_proof"]["fingerprint"] == material.fingerprint

    drifted = {**snapshot, "target_branch": "epic/epic_002"}
    assert review.matching_exact_result_receipt(current, drifted, root=root) is None


def test_acceptance_rejects_generation_advanced_during_proof_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    source_sha, target_sha = "a" * 40, "b" * 40
    merge_sha, observed_target = "c" * 40, "d" * 40
    first = _projection("https://example.test/pulls/12")
    first.update(source_head=source_sha, target_head=target_sha)
    first = review._store_review_generation(
        root,
        "feat_001",
        first,
        generation=1,
        action_id="feature_repair:feat_001:one",
    )
    second = {
        **first,
        "url": "https://example.test/pulls/13",
        "source_head": "e" * 40,
    }

    def advance_generation(*_args, **_kwargs):
        review._store_review_generation(
            root,
            "feat_001",
            second,
            generation=2,
            action_id="feature_repair:feat_001:two",
        )
        return {}

    monkeypatch.setattr(review, "matching_exact_result_receipt", advance_generation)
    snapshot = {
        "state": "merged",
        "url": first["url"],
        "source_branch": first["source_branch"],
        "target_branch": first["target_branch"],
        "source_revision": source_sha,
        "target_revision": observed_target,
        "merge_sha": merge_sha,
        "post_merge_ci": {
            "state": "green",
            "merge_sha": merge_sha,
            "observed_target_sha": observed_target,
        },
    }

    assert not review._accept_current_review_generation(
        "feat_001", first, snapshot, root=root
    )
    current = review.review_record_for_feature("feat_001", root=root)
    assert current is not None
    assert current["current_generation"] == 2
    assert current["url"] == second["url"]
    assert current["closed"] is False
    assert current["reconciliation_status"] == "pending"


def test_new_generation_drops_prior_exact_candidate_proof(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    projection = _projection("https://example.test/pulls/20")
    first = review._store_review_generation(
        root, "feat_001", projection, generation=1, action_id="repair:one"
    )
    review._update_record(
        root,
        "feat_001",
        {
            "candidate_proof_required": True,
            "exact_candidate_proof": {"fingerprint": "old"},
        },
    )

    second = review._store_review_generation(
        root,
        "feat_001",
        {**projection, "url": "https://example.test/pulls/21"},
        generation=2,
        action_id="repair:two",
    )

    assert first["generation"] == 1
    assert "candidate_proof_required" not in second
    assert "exact_candidate_proof" not in second


def test_post_merge_evidence_is_independent_bounded_and_generation_fenced(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    source_sha, target_sha = "a" * 40, "b" * 40
    merge_sha, observed_target = "c" * 40, "d" * 40
    current = _projection("https://example.test/pulls/30")
    current.update(source_head=source_sha, target_head=target_sha)
    review._store_review_generation(
        root, "feat_001", current, generation=1, action_id="repair:one"
    )
    snapshot = {
        "state": "merged",
        "url": current["url"],
        "source_branch": current["source_branch"],
        "target_branch": current["target_branch"],
        "source_revision": source_sha,
        "target_revision": observed_target,
        "merge_sha": merge_sha,
        "review_health": {"state": "terminal", "reason": "merged"},
        "required_check_policy": {
            "available": True,
            "source_head": source_sha,
            "target_head": observed_target,
            "required": ["tests"],
        },
        "required_check_results": {
            "available": True,
            "source_head": source_sha,
            "statuses": {"tests": "success"},
            "checks": {
                "tests": {
                    "status": "success",
                    "generation": 1,
                    "source_head": source_sha,
                }
            },
        },
        "accepted_merge_identity": {
            "available": True,
            "review_url": current["url"],
            "source_branch": current["source_branch"],
            "target_branch": current["target_branch"],
            "source_revision": source_sha,
            "merge_sha": merge_sha,
            "observed_target_head": observed_target,
        },
        "post_merge_ci": {
            "state": "red",
            "merge_sha": merge_sha,
            "observed_target_sha": observed_target,
            "required_check_policy": {
                "available": True,
                "target_head": observed_target,
                "required": ["tests"],
            },
            "required_check_results": {
                "available": True,
                "source_head": merge_sha,
                "target_head": observed_target,
                "statuses": {"tests": "failure"},
                "checks": {
                    "tests": {
                        "status": "failure",
                        "generation": {"pipeline_id": 9, "job_id": 12},
                        "identity": {"name": "tests", "app_id": 7},
                        "source_head": merge_sha,
                    }
                },
            },
        },
        "review_feedback": {"available": True, "actionable": False},
    }

    assert review.record_feature_review_evidence("feat_001", snapshot, root=root)
    persisted = review.review_record_for_feature("feat_001", root=root)
    assert persisted is not None
    assert persisted["prospective_result"]["source_sha"] == source_sha
    assert persisted["accepted_merge_identity"]["merge_sha"] == merge_sha
    assert persisted["post_merge_ci"]["state"] == "red"
    exact = persisted["post_merge_ci"]["required_check_results"]["checks"]["tests"]
    assert exact["generation"] == {"pipeline_id": 9, "job_id": 12}
    assert exact["identity"] == {"name": "tests", "app_id": 7}
    assert persisted["observed_target_sha"] == observed_target

    assert review.record_feature_review_evidence("feat_001", snapshot, root=root)
    duplicate = review.review_record_for_feature("feat_001", root=root)
    assert duplicate is not None
    assert duplicate["review_evidence_revision"] == 2
    assert duplicate["post_merge_ci"] == persisted["post_merge_ci"]

    newer = {**current, "url": "https://example.test/pulls/31"}
    review._store_review_generation(
        root, "feat_001", newer, generation=2, action_id="repair:two"
    )
    assert not review.record_feature_review_evidence("feat_001", snapshot, root=root)
    latest = review.review_record_for_feature("feat_001", root=root)
    assert latest is not None
    assert latest["current_generation"] == 2
    assert latest["url"] == newer["url"]
    assert "post_merge_ci" not in latest


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
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    monkeypatch.setattr(review, "locate_trunk", lambda value: Path(value))
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)
    monkeypatch.setattr(
        review,
        "get_integration_worktree",
        lambda _root, _tier, _id: SimpleNamespace(path=root),
    )
    monkeypatch.setattr(
        "cascade.stacked_dispatch.review_target_branch",
        lambda *_a, **_k: "epic/epic_001",
    )
    monkeypatch.setattr(
        "cascade.feature.publication.prepare_feature_publication",
        lambda *_a, **_k: SimpleNamespace(remote_lease_sha=None),
    )
    monkeypatch.setattr(review, "push_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "cascade.feature.repair.current_feature_repair_record",
        lambda *_a, **_k: {
            "generation": 1,
            "action_id": "feature_repair:feat_001:one",
            "repair_route": "open_review",
            "review_generation": 0,
            "review_url": "https://example.test/pulls/1",
            "review_forge": "github",
            "source_ref": "feat/feat_001",
            "target_ref": "epic/epic_001",
            "source_head": "source-head",
            "target_head": "target-head",
        },
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
        review,
        "merge_request_snapshot",
        lambda *_a, **_k: {
            "state": "open",
            "url": mr.url,
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_revision": "source-head",
            "target_revision": "target-head",
        },
    )
    monkeypatch.setattr(review, "find_merge_request", lambda *_a, **_k: None)
    monkeypatch.setattr(
        review,
        "create_merge_request",
        lambda *_a, **_k: pytest.fail("open review must be reused"),
    )

    refreshed = review.ensure_feature_review("feat_001", root=root)

    assert refreshed is not None and refreshed.url == mr.url
    current = review.review_record_for_feature("feat_001", root=root)
    assert current["current_generation"] == 1
    assert current["route"] == "refresh"
    assert current["previous_review_url"] == mr.url
    assert review.feature_review_generation("feat_001", 0, root=root)["url"] == mr.url

    monkeypatch.setattr(
        review,
        "merge_request_snapshot",
        lambda *_a, **_k: {
            "state": "open",
            "url": mr.url,
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_revision": current["source_head"],
            "target_revision": current["target_head"],
        },
    )
    monkeypatch.setattr(
        review,
        "push_branch",
        lambda *_a, **_k: pytest.fail("checkpoint replay must not push again"),
    )
    replay = review.ensure_feature_review("feat_001", root=root)
    assert replay is not None and replay.url == mr.url


def test_changed_review_source_head_is_refused_before_repair_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path)
    _repair_publication_board(root, monkeypatch)
    current = _projection("https://example.test/pulls/2")
    review._store_review_generation(
        root,
        "feat_001",
        current,
        generation=1,
        action_id="feature_repair:feat_001:one",
    )
    monkeypatch.setattr(
        "cascade.feature.repair.current_feature_repair_record",
        lambda *_a, **_k: {
            "generation": 1,
            "action_id": "feature_repair:feat_001:one",
            "repair_route": "open_review",
            "review_generation": 0,
            "review_url": current["url"],
            "review_forge": "github",
            "source_ref": "feat/feat_001",
            "target_ref": "epic/epic_001",
            "source_head": "source-head",
            "target_head": "target-head",
        },
    )
    monkeypatch.setattr(
        review,
        "merge_request_snapshot",
        lambda *_a, **_k: {
            "state": "open",
            "url": current["url"],
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_revision": "unexpected-moving-head",
            "target_revision": "target-head",
        },
    )

    with pytest.raises(review.GitError, match="authoritative forge facts"):
        review.ensure_feature_review("feat_001", root=root)


def test_changed_review_target_head_is_refused_before_repair_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _repair_publication_board(root, monkeypatch)
    current = _projection("https://example.test/pulls/1")
    review._store_review_generation(
        root, "feat_001", current, generation=0, action_id=None
    )
    monkeypatch.setattr(
        review,
        "merge_request_snapshot",
        lambda *_a, **_k: {
            "state": "open",
            "url": current["url"],
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_revision": "source-head",
            "target_revision": "moved-target-head",
        },
    )
    monkeypatch.setattr(
        review,
        "push_branch",
        lambda *_a, **_k: pytest.fail("stale target refusal must precede push"),
    )

    with pytest.raises(review.GitError, match="target head changed"):
        review.ensure_feature_review("feat_001", root=root)


def test_changed_original_review_identity_refuses_before_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _repair_publication_board(root, monkeypatch)
    old = _projection("https://example.test/pulls/1")
    review._store_review_generation(root, "feat_001", old, generation=0, action_id=None)
    monkeypatch.setattr(
        "cascade.feature.repair.current_feature_repair_record",
        lambda *_a, **_k: {
            "generation": 1,
            "action_id": "feature_repair:feat_001:one",
            "repair_route": "open_review",
            "review_generation": 0,
            "review_url": "https://example.test/pulls/99",
            "review_forge": "github",
            "source_ref": "feat/feat_001",
            "target_ref": "epic/epic_001",
            "source_head": "source-head",
            "target_head": "target-head",
        },
    )
    monkeypatch.setattr(
        review,
        "push_branch",
        lambda *_a, **_k: pytest.fail("identity refusal must precede push"),
    )

    with pytest.raises(review.GitError, match="identity changed"):
        review.ensure_feature_review("feat_001", root=root)


def test_merged_original_review_refuses_scoped_repair_without_creating_follow_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _repair_publication_board(root, monkeypatch)
    old = _projection("https://example.test/pulls/1")
    review._store_review_generation(root, "feat_001", old, generation=0, action_id=None)
    old_mr = review._record_to_mr(old)
    monkeypatch.setattr(
        review,
        "merge_request_snapshot",
        lambda *_a, **_k: {
            "state": "merged",
            "url": old_mr.url,
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_revision": "source-head",
            "target_revision": "target-head",
            "merge_sha": "merge-zero",
        },
    )
    monkeypatch.setattr(review, "find_merge_request", lambda *_a, **_k: None)
    monkeypatch.setattr(
        review,
        "create_merge_request",
        lambda *_a, **_k: pytest.fail("terminal review must not create a follow-up"),
    )

    with pytest.raises(review.GitError, match="no longer open"):
        review.ensure_feature_review("feat_001", root=root)

    current = review.review_record_for_feature("feat_001", root=root)
    assert current["current_generation"] == 0
    assert current["url"] == old_mr.url


def test_follow_up_save_failure_recovers_same_remote_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _repair_publication_board(root, monkeypatch)
    monkeypatch.setattr(
        "cascade.feature.repair.current_feature_repair_record",
        lambda *_a, **_k: {
            "generation": 1,
            "action_id": "feature_repair:feat_001:legacy",
        },
    )
    old = _projection("https://example.test/pulls/1")
    review._store_review_generation(root, "feat_001", old, generation=0, action_id=None)

    def snapshot_for_review(_root, mr):
        if mr.url == old["url"]:
            return {
                "state": "merged",
                "url": old["url"],
                "source_branch": "feat/feat_001",
                "target_branch": "epic/epic_001",
                "source_revision": "source-head",
                "merge_sha": "merge-zero",
            }
        return {
            "state": "open",
            "url": mr.url,
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_revision": review.head_sha(root),
            "target_revision": review.head_sha(root),
        }

    monkeypatch.setattr(review, "merge_request_snapshot", snapshot_for_review)
    follow_up = MergeRequest(
        url="https://example.test/pulls/2",
        number="2",
        forge="github",
        source_branch="feat/feat_001",
        target_branch="epic/epic_001",
        draft=False,
    )
    created: list[MergeRequest] = []
    monkeypatch.setattr(
        review,
        "create_merge_request",
        lambda *_a, **_k: created.append(follow_up) or follow_up,
    )
    monkeypatch.setattr(
        review,
        "find_merge_request",
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
    assert (
        review.review_record_for_feature("feat_001", root=root)["current_generation"]
        == 1
    )


def _completed_delivery_board(root: Path) -> None:
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
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


def test_delivery_view_retains_completed_owner_for_original_open_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _completed_delivery_board(root)
    review._store_review_generation(
        root,
        "feat_001",
        _projection("https://example.test/pulls/1"),
        generation=0,
        action_id=None,
    )
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)
    monkeypatch.setattr(
        review,
        "merge_request_snapshot",
        lambda *_a, **_k: pytest.fail("delivery reads must not poll the forge"),
    )
    before = (root / ".cascade/reviews.json").read_bytes()

    first = review.feature_delivery_view("feat_001", root=root)
    second = review.feature_delivery_views(["feat_001"], root=root)["feat_001"]

    assert first == second
    assert first == {
        "feature_id": "feat_001",
        "accountable_owner": "feature_team:feat_001",
        "phase": "review_pending",
        "review_url": "https://example.test/pulls/1",
        "generation": 0,
        "published_generation": 0,
        "evidence_status": "open",
        "blocker": "review_acceptance_pending",
        "next_prerequisite": "await_current_review_acceptance",
        "actionable": False,
    }
    assert (root / ".cascade/reviews.json").read_bytes() == before


@pytest.mark.parametrize(
    ("record", "expected_phase", "expected_status"),
    [
        (None, "implementation_ready", "review_evidence_missing"),
        (
            _projection("https://example.test/pulls/7", closed=True),
            "merge_verification_pending",
            "legacy_unverified",
        ),
        (
            {**_projection("https://example.test/pulls/8"), "state": "closed"},
            "merge_verification_pending",
            "legacy_unverified",
        ),
    ],
)
def test_delivery_view_keeps_missing_and_closed_unmerged_evidence_nonterminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record: dict[str, object] | None,
    expected_phase: str,
    expected_status: str,
) -> None:
    root = make_repo(tmp_path)
    _completed_delivery_board(root)
    if record is not None:
        review._store_review_generation(
            root, "feat_001", record, generation=0, action_id=None
        )
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)

    view = review.feature_delivery_view("feat_001", root=root)

    assert view["phase"] == expected_phase
    assert view["evidence_status"] == expected_status
    assert view["blocker"] is not None


@pytest.mark.parametrize(
    ("repair_phase", "expected_phase"),
    [
        ("authority_recorded", "repair_requested"),
        ("parent_enabled", "repair_in_progress"),
        ("delivery_pending", "repair_in_progress"),
    ],
)
def test_delivery_view_projects_current_admitted_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repair_phase: str,
    expected_phase: str,
) -> None:
    root = make_repo(tmp_path)
    _completed_delivery_board(root)
    review._store_review_generation(
        root,
        "feat_001",
        _projection("https://example.test/pulls/1"),
        generation=0,
        action_id=None,
    )
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)
    monkeypatch.setattr(
        "cascade.feature.repair.current_feature_repair_record",
        lambda *_a, **_k: {
            "generation": 1,
            "phase": repair_phase,
            "next_action": "resume_original_task_delivery",
        },
    )

    view = review.feature_delivery_view("feat_001", root=root)

    assert view["phase"] == expected_phase
    assert view["generation"] == 1
    assert view["published_generation"] == 0
    assert view["actionable"] is True
    assert view["review_url"] == "https://example.test/pulls/1"


def test_delivery_view_requires_current_acceptance_target_ancestry_and_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _completed_delivery_board(root)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "delivery fixture"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "branch", "feat/feat_001", head], cwd=root, check=True)
    subprocess.run(["git", "branch", "epic/epic_001", head], cwd=root, check=True)
    projection = {
        **_projection("https://example.test/pulls/9", closed=True),
        "source_head": head,
        "target_head": head,
    }
    review._store_review_generation(
        root, "feat_001", projection, generation=1, action_id="repair:one"
    )
    review._update_record(
        root,
        "feat_001",
        {
            "accepted_merge_sha": head,
            "accepted_source_head": head,
            "accepted_target_head": head,
            "reconciliation_status": "accepted",
        },
    )
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)

    pending = review.feature_delivery_view("feat_001", root=root)
    assert pending["phase"] == "merge_verification_pending"
    assert pending["blocker"] == "completion_event_missing"

    append_event(
        "epic_001",
        Event(
            type="FeatureCompleted",
            ts=datetime.now(timezone.utc),
            payload={"feature_id": "feat_001"},
            dest="epic_001",
        ),
        root=root,
    )

    integrated = review.feature_delivery_view("feat_001", root=root)
    assert integrated["phase"] == "verified_integrated"
    assert integrated["evidence_status"] == "accepted_current_generation"
    assert integrated["blocker"] is None

    (root / ".cascade/reviews.json").unlink()
    monkeypatch.setattr(review, "review_enabled", lambda _root: False)
    local = review.feature_delivery_view("feat_001", root=root)
    assert local["phase"] == "verified_integrated"
    assert local["evidence_status"] == "local_integration"


def test_delivery_view_requires_exact_supported_cancellation_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="cancelled",
        parent="epic_001",
    )
    cancelled_at = datetime.now(timezone.utc)
    child = read_doc("feat_001", root=root)
    child.meta.cancellation_reason = "scope withdrawn"
    child.meta.cancelled_at = cancelled_at
    child.meta.cancellation_step = "complete"
    write_doc(child, root=root)
    parent = read_doc("epic_001", root=root)
    parent.meta.cancellation_feedback.append(
        CancellationFeedback(
            child_id="feat_001",
            child_tier="feature",
            parent_id="epic_001",
            reason="scope withdrawn",
            cancelled_at=cancelled_at,
            disposition="continue_reduced_scope",
            resolved_at=datetime.now(timezone.utc),
        )
    )
    write_doc(parent, root=root)
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)

    view = review.feature_delivery_view("feat_001", root=root)

    assert view["phase"] == "terminal_cancelled"
    assert view["evidence_status"] == "explicit_terminal_disposition"
    assert view["blocker"] is None
