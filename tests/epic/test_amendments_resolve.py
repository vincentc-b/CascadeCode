"""resolve_amendment (task_028)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import cascade.epic.amendments  # noqa: F401 — registers tool
from cascade.amendments import extract_section_body, read_amendment
from cascade.epic.amendments import ResolveAmendmentError, resolve_amendment
from cascade.feature.amendments import ack_amendment, propose_epic_amendment
from cascade.watchdog import read_events
from tests.support import EPIC_BODY, add_doc, make_repo
from cascade.board.store import pin_parent, read_doc, write_doc


@pytest.fixture
def board(tmp_path: Path) -> dict[str, object]:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    epic = read_doc("epic_001", root=root)
    epic.body = EPIC_BODY
    write_doc(epic, root=root)
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    pin_parent("feat_001", "epic_001", root=root)
    return {"root": root}


def _propose(root: Path) -> str:
    return propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "Feature-owned write paths only.",
        "Need tighter isolation.",
        feature_id="feat_001",
        root=root,
    )


def test_accept_commits_epic_and_unblocks_feature(board: dict[str, object]) -> None:
    root = board["root"]
    amd_id = _propose(root)
    epic = read_doc("epic_001", root=root)
    rel = epic.meta.path.relative_to(root).as_posix()

    sha = resolve_amendment(amd_id, "accept", epic_id="epic_001", root=root)
    assert sha is not None
    assert len(sha) == 40

    epic_after = read_doc("epic_001", root=root)
    section = extract_section_body(epic_after.body, "Cross-module constraints")
    assert section.strip() == "Feature-owned write paths only."
    assert f"`{amd_id}`" in epic_after.body
    assert "**accepted**" in epic_after.body
    assert "feat_001" in epic_after.body

    log_sha = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", rel],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert log_sha == sha

    record = read_amendment(amd_id, root=root)
    assert record.state == "accepted"

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "active"
    assert feature.meta.parent_rev == sha

    events, _ = read_events("feat_001", 0, root=root)
    approved = [e for e in events if e.type == "AmendmentApproved"]
    assert len(approved) == 1
    assert approved[0].payload == {
        "feature_id": "feat_001",
        "epic_id": "epic_001",
        "epic_rev": sha,
    }


def test_reject_leaves_epic_unchanged_and_logs_feature_decision(board: dict[str, object]) -> None:
    root = board["root"]
    amd_id = _propose(root)
    epic_before = read_doc("epic_001", root=root).body

    result = resolve_amendment(
        amd_id,
        "reject",
        note="Constraints already sufficient.",
        epic_id="epic_001",
        root=root,
    )
    assert result is None

    epic_after = read_doc("epic_001", root=root)
    assert epic_after.body == epic_before

    record = read_amendment(amd_id, root=root)
    assert record.state == "rejected"

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "active"

    events, _ = read_events("feat_001", 0, root=root)
    rejected = [e for e in events if e.type == "AmendmentRejected"]
    assert len(rejected) == 1
    assert rejected[0].payload["reason"] == "Constraints already sufficient."

    assert "NOT auto-unblocked for dispatch" in feature.body
    assert "revise or replace" in feature.body


def test_revise_then_ack_then_accept(board: dict[str, object]) -> None:
    root = board["root"]
    amd_id = _propose(root)

    assert (
        resolve_amendment(
            amd_id,
            "revise",
            revised_text="Counter-proposed constraints.",
            epic_id="epic_001",
            root=root,
        )
        is None
    )
    record = read_amendment(amd_id, root=root)
    assert record.state == "revise_pending"
    assert read_doc("feat_001", root=root).meta.status == "blocked"

    with pytest.raises(ResolveAmendmentError, match="awaits feature ack"):
        resolve_amendment(amd_id, "accept", epic_id="epic_001", root=root)

    ack_amendment(amd_id, feature_id="feat_001", root=root)
    record = read_amendment(amd_id, root=root)
    assert record.state == "pending"
    assert record.proposed_text == "Counter-proposed constraints."
    assert read_doc("feat_001", root=root).meta.status == "blocked"

    sha = resolve_amendment(amd_id, "accept", epic_id="epic_001", root=root)
    assert sha is not None
    epic = read_doc("epic_001", root=root)
    section = extract_section_body(epic.body, "Cross-module constraints")
    assert section.strip() == "Counter-proposed constraints."


def test_resolve_fails_closed_on_wrong_epic_and_terminal_state(
    board: dict[str, object],
) -> None:
    root = board["root"]
    add_doc(root, id="epic_002", title="Other epic", tier="epic", status="active")
    amd_id = _propose(root)
    resolve_amendment(amd_id, "reject", epic_id="epic_001", root=root)

    with pytest.raises(ResolveAmendmentError, match="belongs to epic_001"):
        resolve_amendment(amd_id, "accept", epic_id="epic_002", root=root)

    with pytest.raises(ResolveAmendmentError, match="already rejected"):
        resolve_amendment(amd_id, "accept", epic_id="epic_001", root=root)


def test_accept_retry_finishes_unblock_when_already_accepted(
    board: dict[str, object],
) -> None:
    root = board["root"]
    amd_id = _propose(root)
    sha = resolve_amendment(amd_id, "accept", epic_id="epic_001", root=root)
    assert sha is not None

    feature = read_doc("feat_001", root=root)
    feature.meta.status = "blocked"
    write_doc(feature, root=root)

    sha_retry = resolve_amendment(amd_id, "accept", epic_id="epic_001", root=root)
    assert sha_retry == sha
    assert read_doc("feat_001", root=root).meta.status == "active"
    assert read_doc("feat_001", root=root).meta.parent_rev == sha


def test_reject_retry_finishes_unblock_when_already_rejected(
    board: dict[str, object],
) -> None:
    root = board["root"]
    amd_id = _propose(root)
    resolve_amendment(amd_id, "reject", epic_id="epic_001", root=root)

    feature = read_doc("feat_001", root=root)
    feature.meta.status = "blocked"
    write_doc(feature, root=root)

    assert resolve_amendment(amd_id, "reject", epic_id="epic_001", root=root) is None
    assert read_doc("feat_001", root=root).meta.status == "active"


def test_revise_requires_revised_text(board: dict[str, object]) -> None:
    root = board["root"]
    amd_id = _propose(root)
    with pytest.raises(ResolveAmendmentError, match="revised_text"):
        resolve_amendment(amd_id, "revise", epic_id="epic_001", root=root)
