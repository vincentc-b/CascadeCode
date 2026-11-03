"""Accepted stale stacked reviews are held for Epic Team reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

import cascade.review as review
from cascade.stacked_review_recovery import (
    classify_stacked_review_integration_gap,
    persist_stacked_review_integration_gap,
)
from cascade.task.action_recovery import load_action
from cascade.workspace.integration_worktree import integration_branch
from tests.support import add_doc, make_repo


def _review(feature_id: str, target_branch: str, *, closed: bool = False) -> dict[str, object]:
    return {
        "url": f"https://github.example/o/r/pull/{feature_id}",
        "number": feature_id.removeprefix("feat_"),
        "forge": "github",
        "source_branch": integration_branch("feature", feature_id),
        "target_branch": target_branch,
        "draft": False,
        "closed": closed,
    }


def _stacked_board(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root, id="feat_001", title="Predecessor", tier="feature", status="completed", parent="epic_001"
    )
    add_doc(
        root,
        id="feat_002",
        title="Stacked child",
        tier="feature",
        status="active",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    (root / ".cascade").mkdir(exist_ok=True)
    (root / ".cascade" / "reviews.json").write_text(
        json.dumps(
            {
                "feat_001": _review("feat_001", "epic/epic_001", closed=True),
                "feat_002": _review("feat_002", "feat/feat_001"),
            }
        ),
        encoding="utf-8",
    )


def test_classifies_and_persists_accepted_review_gap_once(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _stacked_board(root)
    record = review.review_record_for_feature("feat_002", root=root)
    assert record is not None

    assert classify_stacked_review_integration_gap(
        "feat_002", record, root=root, accepted=False
    ) is None
    gap = classify_stacked_review_integration_gap("feat_002", record, root=root, accepted=True)
    assert gap is not None
    assert gap.predecessor_id == "feat_001"
    assert gap.expected_target_branch == "epic/epic_001"

    first = persist_stacked_review_integration_gap(gap, root=root)
    second = persist_stacked_review_integration_gap(gap, root=root)
    assert first == second
    action = load_action("feat_002:stacked_review_integration_gap", root=root)
    assert action is not None
    assert action["action_kind"] == "stacked_review_integration_gap"
    assert action["recovery_state"] == "awaiting_owner_decision"
    assert action["owner_decisions"][0]["owner"] == "epic_team"
    evidence = action["metadata"]
    assert evidence["accepted_review"] == {
        "url": "https://github.example/o/r/pull/feat_002",
        "number": "002",
        "forge": "github",
        "source_branch": "feat/feat_002",
        "target_branch": "feat/feat_001",
    }


def test_merged_stale_review_is_not_closed_or_completed(tmp_path: Path, monkeypatch) -> None:
    root = make_repo(tmp_path, git=False)
    _stacked_board(root)
    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda *_args, **_kwargs: {"state": "merged", "comments": []},
    )

    review.poll_feature_reviews(root)

    records = json.loads((root / ".cascade" / "reviews.json").read_text(encoding="utf-8"))
    assert records["feat_002"].get("closed") is not True
    assert load_action("feat_002:stacked_review_integration_gap", root=root) is not None
