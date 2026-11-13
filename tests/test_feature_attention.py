"""Durable Feature attention bootstrap, provenance, and recovery."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

import cascade.feature_attention as attention_store
from cascade.board.context import set_project_context
from cascade.board.store import list_board, read_doc
from cascade.board.types import BoardIndex
from cascade.epic.mint import mint_feature
from cascade.feature_attention import (
    AttentionUnavailable,
    feature_attention_paths,
    feature_attention_transaction,
    initialize_feature_attention,
    read_feature_attention,
)
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, declare_no_dependencies, make_repo


def test_first_rollout_records_history_and_only_open_active_children_as_new(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    add_doc(root, id="epic_002", title="Cancelling", tier="epic", status="cancelling")
    add_doc(root, id="epic_003", title="Done", tier="epic", status="completed")
    add_doc(
        root,
        id="feat_001_001",
        title="Needs attention",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_001_002",
        title="Already active",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002_001",
        title="Cancelling parent",
        tier="feature",
        status="ready_to_plan",
        parent="epic_002",
    )
    add_doc(
        root,
        id="feat_003_001",
        title="Historical",
        tier="feature",
        status="completed",
        parent="epic_003",
    )

    snapshot = initialize_feature_attention(root)

    assert snapshot.state == "available"
    assert snapshot.revision == 1
    records = snapshot.ledger["features"]  # type: ignore[index]
    assert set(records) == {
        "feat_001_001",
        "feat_001_002",
        "feat_002_001",
        "feat_003_001",
    }
    assert records["feat_001_001"]["attention_eligible"] is True
    assert all(
        records[feature_id]["attention_eligible"] is False
        for feature_id in ("feat_001_002", "feat_002_001", "feat_003_001")
    )
    assert {record["provenance"] for record in records.values()} == {"baseline"}
    paths = feature_attention_paths(root)
    assert paths.ledger.is_file() and paths.marker.is_file()


def test_split_workspace_uses_tracking_trunk_for_one_shared_ledger(
    tmp_path: Path,
) -> None:
    target = make_repo(tmp_path / "target", git=False)
    tracking = make_repo(tmp_path / "tracking", git=False)
    set_project_context(ProjectContext.split(target, tracking))
    try:
        add_doc(target, id="epic_001", title="Epic", tier="epic", status="active")
        add_doc(
            target,
            id="feat_001_001",
            title="Feature",
            tier="feature",
            parent="epic_001",
        )

        from_target = initialize_feature_attention(target)
        from_tracking = read_feature_attention(tracking)

        assert from_target.ledger == from_tracking.ledger
        assert (
            feature_attention_paths(target).ledger
            == feature_attention_paths(tracking).ledger
        )
        assert feature_attention_paths(target).ledger.is_relative_to(tracking)
        assert not (target / ".cascade" / "feature_attention.json").exists()
    finally:
        set_project_context(None)


def test_interrupted_bootstrap_finalizes_marker_without_rebaselining(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001_001",
        title="Original",
        tier="feature",
        parent="epic_001",
    )
    real_write_marker = attention_store._write_marker

    def fail_marker(_path: Path) -> None:
        raise OSError("simulated marker crash")

    monkeypatch.setattr(attention_store, "_write_marker", fail_marker)
    interrupted = initialize_feature_attention(root)
    assert interrupted.state == "unavailable"
    assert feature_attention_paths(root).ledger.is_file()
    assert not feature_attention_paths(root).marker.exists()

    add_doc(
        root,
        id="feat_001_002",
        title="After commit",
        tier="feature",
        parent="epic_001",
    )
    monkeypatch.setattr(attention_store, "_write_marker", real_write_marker)
    recovered = initialize_feature_attention(root)

    assert recovered.state == "available"
    assert recovered.revision == 2
    records = recovered.ledger["features"]  # type: ignore[index]
    assert records["feat_001_001"]["provenance"] == "baseline"
    assert records["feat_001_002"]["provenance"] == "discovered"


def test_interrupted_first_commit_with_no_artifacts_can_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    real_atomic_json = attention_store._atomic_json
    failed = False

    def fail_first(path: Path, value: dict[str, object]) -> None:
        nonlocal failed
        if path.name == attention_store.LEDGER_NAME and not failed:
            failed = True
            raise OSError("simulated pre-replace crash")
        real_atomic_json(path, value)

    monkeypatch.setattr(attention_store, "_atomic_json", fail_first)
    interrupted = initialize_feature_attention(root)
    paths = feature_attention_paths(root)
    assert interrupted.state == "unavailable"
    assert not paths.ledger.exists()
    assert not paths.marker.exists()

    recovered = initialize_feature_attention(root)
    assert recovered.state == "available"
    assert recovered.revision == 1


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_initialized_ledger_loss_or_corruption_is_unavailable_without_reset(
    tmp_path: Path, damage: str
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    initialize_feature_attention(root)
    paths = feature_attention_paths(root)
    if damage == "missing":
        paths.ledger.unlink()
    else:
        paths.ledger.write_text("{ definitely not json", encoding="utf-8")
    before = paths.ledger.read_bytes() if paths.ledger.exists() else None

    snapshot = initialize_feature_attention(root)

    assert snapshot.state == "unavailable"
    assert (paths.ledger.read_bytes() if paths.ledger.exists() else None) == before
    assert paths.marker.is_file()


def test_startup_reconciliation_closes_mint_crash_gap_once(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    baseline = initialize_feature_attention(root)
    add_doc(
        root,
        id="feat_001_001",
        title="Persisted before hook",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )

    reconciled = initialize_feature_attention(root)
    replayed = initialize_feature_attention(root)

    record = reconciled.ledger["features"]["feat_001_001"]  # type: ignore[index]
    assert record["provenance"] == "discovered"
    assert record["attention_eligible"] is True
    assert reconciled.revision == baseline.revision + 1  # type: ignore[operator]
    assert replayed.revision == reconciled.revision


def test_mint_records_feature_minted_after_durable_creation(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    declare_no_dependencies("epic_001", root=root)

    feature_id = mint_feature("Corrective feature", epic_id="epic_001", root=root)

    snapshot = read_feature_attention(root)
    record = snapshot.ledger["features"][feature_id]  # type: ignore[index]
    assert record["provenance"] == "FeatureMinted"
    assert record["epic_id"] == "epic_001"
    assert record["attention_eligible"] is True


def test_mint_write_failure_leaves_discoverable_crash_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    declare_no_dependencies("epic_001", root=root)
    initialize_feature_attention(root)
    real_atomic_json = attention_store._atomic_json

    def fail_ledger(path: Path, value: dict[str, object]) -> None:
        if path.name == attention_store.LEDGER_NAME:
            raise OSError("simulated attention persistence failure")
        real_atomic_json(path, value)

    monkeypatch.setattr(attention_store, "_atomic_json", fail_ledger)
    with pytest.raises(AttentionUnavailable, match="attention write failed"):
        mint_feature("Crash gap", epic_id="epic_001", root=root)

    feature_id = "feat_001_001"
    assert read_doc(feature_id, root=root).meta.id == feature_id
    monkeypatch.setattr(attention_store, "_atomic_json", real_atomic_json)
    recovered = initialize_feature_attention(root)
    assert recovered.ledger["features"][feature_id]["provenance"] == "discovered"  # type: ignore[index]


def test_concurrent_mint_records_are_not_lost(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    initialize_feature_attention(root)
    barrier = threading.Barrier(6)
    failures: list[BaseException] = []

    def record(index: int) -> None:
        try:
            barrier.wait()
            with feature_attention_transaction(root, board=BoardIndex()) as transaction:
                transaction.record_feature_minted(f"feat_001_{index:03d}", "epic_001")
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [threading.Thread(target=record, args=(index,)) for index in range(1, 7)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not failures
    snapshot = read_feature_attention(root)
    assert set(snapshot.ledger["features"]) == {  # type: ignore[index]
        f"feat_001_{index:03d}" for index in range(1, 7)
    }
    assert snapshot.revision == 7


def test_reconciliation_preserves_seen_and_first_provenance(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
    )
    initialized = initialize_feature_attention(root)
    paths = feature_attention_paths(root)
    ledger = initialized.ledger
    seen = {
        "actor": "operator@example.test",
        "at": datetime.now(timezone.utc).isoformat(),
    }
    ledger["features"]["feat_001_001"]["seen"] = seen  # type: ignore[index]
    paths.ledger.write_text(json.dumps(ledger) + "\n", encoding="utf-8")

    board = list_board(root)
    board.by_id["feat_001_001"].status = "completed"
    replayed = initialize_feature_attention(root, board=board)

    record = replayed.ledger["features"]["feat_001_001"]  # type: ignore[index]
    assert record["seen"] == seen
    assert record["provenance"] == "baseline"
    assert record["attention_eligible"] is True
    assert replayed.revision == initialized.revision
