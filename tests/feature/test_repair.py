"""Generation-fenced Feature repair admission and watchdog replay."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import cascade.feature.repair as repair
from cascade.board.store import read_doc, write_doc
from cascade.feature.repair import FeatureRepairError, admit_feature_repair
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.loop import _authorized
from cascade.watchdog.types import Event
from tests.support import add_doc, commit_board, make_repo


def _completed_feature(root: Path) -> None:
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


def test_admission_persists_exact_generation_before_active_introduction(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _completed_feature(root)

    result = admit_feature_repair(
        "feat_001",
        "delivery:task_001",
        approval_reference="approval-1",
        scope_reference="scope-1",
        root=root,
    )

    assert result["ok"] is True
    assert result["generation"] == 1
    assert result["phase"] == "parent_enabled"
    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "active"
    assert "cascade-feature-repair:" in feature.body
    assert _authorized(root, feature.meta)
    events, _ = read_events("feat_001", 0, root=root)
    assert [event.type for event in events] == ["FeatureRepairAuthorized"]

    ledger = json.loads((root / ".cascade/executions.json").read_text())
    action = ledger["actions"][result["action_id"]]
    assert action["authority_event_id"] == events[0].payload["event_id"]
    assert action["introduction_commit"]
    assert action["introduction_blob"] == action["intended_document_digest"]


def test_replay_is_idempotent_and_changed_approval_is_refused(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _completed_feature(root)
    first = admit_feature_repair(
        "feat_001", "delivery:task_001", approval_reference="approval-1", root=root
    )
    replay = admit_feature_repair(
        "feat_001", "delivery:task_001", approval_reference="approval-1", root=root
    )
    assert replay["action_id"] == first["action_id"]
    assert replay["replayed"] is True
    events, _ = read_events("feat_001", 0, root=root)
    assert len(events) == 1

    with pytest.raises(FeatureRepairError, match="approval_reference changed"):
        admit_feature_repair(
            "feat_001", "delivery:task_001", approval_reference="approval-2", root=root
        )


def test_restart_after_authority_append_reuses_one_event_and_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _completed_feature(root)
    real_write = repair._write_payload
    calls = 0

    def interrupt_after_event(repo: Path, payload: dict) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected authority checkpoint interruption")
        real_write(repo, payload)

    monkeypatch.setattr(repair, "_write_payload", interrupt_after_event)
    with pytest.raises(OSError, match="checkpoint interruption"):
        admit_feature_repair("feat_001", "delivery:task_001", root=root)

    monkeypatch.setattr(repair, "_write_payload", real_write)
    resumed = admit_feature_repair("feat_001", "delivery:task_001", root=root)
    replay = admit_feature_repair("feat_001", "delivery:task_001", root=root)

    assert replay["action_id"] == resumed["action_id"]
    assert replay["generation"] == resumed["generation"] == 1
    events, _ = read_events("feat_001", 0, root=root)
    authority = [event for event in events if event.type == "FeatureRepairAuthorized"]
    assert len(authority) == 1
    assert authority[0].payload["action_id"] == resumed["action_id"]


def test_watchdog_rejects_event_whose_generation_does_not_match_action(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _completed_feature(root)
    result = admit_feature_repair("feat_001", "delivery:task_001", root=root)
    feature = read_doc("feat_001", root=root)
    action = json.loads((root / ".cascade/executions.json").read_text())["actions"][
        result["action_id"]
    ]
    (root / "docs/_queue/feat_001.jsonl").unlink()
    append_event(
        "feat_001",
        Event(
            type="FeatureRepairAuthorized",
            ts=datetime.now(timezone.utc),
            payload={
                "id": "feat_001",
                "feature_id": "feat_001",
                "epic_id": "epic_001",
                "action_id": result["action_id"],
                "generation": 2,
                "event_id": action["authority_event_id"],
                "owner_fingerprint": action["owner_fingerprint"],
                "source_ref": action["source_ref"],
                "target_ref": action["target_ref"],
                "intended_active_path": action["intended_active_path"],
                "document_digest": action["intended_document_digest"],
            },
            dest="feat_001",
        ),
        root=root,
    )
    assert not _authorized(root, feature.meta)


def test_watchdog_binds_introduction_but_allows_later_marked_feature_edit(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _completed_feature(root)
    admit_feature_repair("feat_001", "delivery:task_001", root=root)
    feature = read_doc("feat_001", root=root)
    feature.body += "\nA later scoped planning note.\n"
    write_doc(feature, root=root)
    assert _authorized(root, read_doc("feat_001", root=root).meta)

    feature = read_doc("feat_001", root=root)
    feature.body = "\n".join(
        line
        for line in feature.body.splitlines()
        if "cascade-feature-repair:" not in line
    )
    write_doc(feature, root=root)
    assert not _authorized(root, read_doc("feat_001", root=root).meta)


def test_admission_refuses_missing_approval_without_moving_feature(
    tmp_path: Path,
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
    commit_board(root)
    with pytest.raises(FeatureRepairError, match="approval is missing"):
        admit_feature_repair("feat_001", "delivery:task_001", root=root)
    assert read_doc("feat_001", root=root).meta.status == "completed"
