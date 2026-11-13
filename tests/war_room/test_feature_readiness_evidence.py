"""Versioned board explanation and actual feature-dispatch evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cascade.board.store import read_doc, write_doc
from cascade.feature.readiness import compute_feature_readiness
from cascade.feature.readiness_evidence import (
    SOURCES,
    approval_evidence,
    read_dispatch_attempt,
    write_approval_evidence,
)
from cascade.war_room.serialize import feature_readiness_to_dict
from cascade.watchdog import dispatch_feature
from cascade.workspace.integration_worktree import merged_board
from tests.support import add_doc, make_repo


def _board(root: Path):
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
    )
    return merged_board(root)


def test_explanation_v1_has_six_revision_sources_and_reason_sources(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    board = _board(root)
    meta = board.by_id["feat_001"]
    readiness = compute_feature_readiness(
        meta.id,
        root=root,
        board=board,
        pending_review_ids=frozenset(),
        review_refusals={},
        approval_state="current",
    )
    assert readiness is not None

    payload = feature_readiness_to_dict(
        readiness,
        meta=meta,
        board=board,
        root=root,
        approval_state="current",
        approval_revision="approval-revision",
        provider_readiness={
            "outcome": "supported",
            "selection_fingerprint": "selection-revision",
            "inventory_freshness": {
                "stale": False,
                "fetched_at": 1.0,
                "expires_at": 2.0,
            },
        },
    )

    explanation = payload["explanation"]
    assert explanation["version"] == 1
    assert explanation["evaluated_at"].endswith("+00:00")
    assert tuple(explanation["sources"]) == SOURCES
    assert explanation["primary_reason_code"] == "not_approved"
    reason = explanation["reasons"][0]
    assert reason["source_ids"] == ["board", "approval"]
    assert reason["links"] == [
        {"label": "Open feat_001 plan", "href": "/plan/feat_001"}
    ]
    assert explanation["last_dispatch_attempt"] is None


def test_actual_refusal_is_recorded_but_board_projection_does_not_write(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    board = _board(root)
    attempts = root / ".cascade" / "feature_dispatch_attempts.json"

    readiness = compute_feature_readiness(
        "feat_001",
        root=root,
        board=board,
        pending_review_ids=frozenset(),
        review_refusals={},
        approval_state="current",
    )
    assert readiness is not None
    feature_readiness_to_dict(
        readiness,
        meta=board.by_id["feat_001"],
        board=board,
        root=root,
        approval_state="current",
        approval_revision="approval-revision",
        provider_readiness=None,
    )
    assert not attempts.exists()

    first = dispatch_feature("feat_001", "human", root=root)
    assert first.ok is False
    assert first.reason == "not_approved"
    record = read_dispatch_attempt("feat_001", root=root)
    assert record is not None
    assert record["outcome"] == "refused"
    assert record["reason_code"] == "not_approved"
    assert set(record["source_revisions"]) == set(SOURCES)

    second = dispatch_feature("feat_001", "human", root=root)
    assert second.ok is False
    later = read_dispatch_attempt("feat_001", root=root)
    assert later is not None
    assert later["sequence"] > record["sequence"]
    assert later["attempt_id"] > record["attempt_id"]


def test_approval_evidence_is_bound_to_current_plan_body(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _board(root)
    doc = read_doc("feat_001", root=root)
    doc.meta.approved_at = datetime.now(timezone.utc)
    write_doc(doc, root=root)
    write_approval_evidence(doc.meta, root=root)
    assert approval_evidence(doc.meta, root=root)[0] == "current"

    changed = read_doc("feat_001", root=root)
    changed.body += "\nPlan revision changed.\n"
    write_doc(changed, root=root)
    assert approval_evidence(changed.meta, root=root)[0] == "stale"
