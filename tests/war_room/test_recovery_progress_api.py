from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

from cascade.recovery_progress.publisher import publish_committed_transition
from cascade.board.context import set_project_context
from cascade.watchdog.incidents import transition_receipt_v1
from cascade.war_room.recovery_progress import (
    RecoveryProgressRequestError,
    RecoveryProgressRevisionChanged,
    board_recovery_projection,
    read_recovery_progress,
)
from tests.support import make_repo
from cascade.workspace.types import ProjectContext


def _receipt(index: int, *, work_id: str = "task_001") -> dict[str, object]:
    action_id = f"{work_id}:recovery:{index:03d}"
    return transition_receipt_v1(
        source_kind="task_action",
        source_key=action_id,
        action="recovery",
        action_id=action_id,
        generation=f"sha256:generation-{index:03d}",
        graph_id=work_id,
        affected_work_ids=[work_id],
        attempt_number=index + 1,
        claim_id=f"claim-{index}",
        sequence=1,
        transition_kind="created",
        occurred_at=f"2026-11-25T00:{index % 60:02d}:00+00:00",
        source_reference=f"fixture:{index}",
        safe_payload={"target": work_id},
    )


def _publish(root: Path, count: int, *, work_id: str = "task_001") -> None:
    for index in range(count):
        publish_committed_transition(root, _receipt(index, work_id=work_id), {})


def test_bounded_reader_paginates_and_keeps_one_revision_primary(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    _publish(root, 60)

    first = read_recovery_progress(root, "task_001")
    assert first["schema_version"] == 1
    assert first["entry_count"] == 60
    assert len(first["items"]) == 50
    assert first["primary"] == first["items"][0]
    cursor = first["next_cursor"]
    assert isinstance(cursor, str)

    second = read_recovery_progress(root, "task_001", cursor=cursor)
    assert second["revision"] == first["revision"]
    assert second["primary"] == first["primary"]
    assert len(second["items"]) == 10
    assert second["next_cursor"] is None


def test_cursor_is_exact_work_and_revision_bound(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _publish(root, 51)
    cursor = read_recovery_progress(root, "task_001")["next_cursor"]
    assert isinstance(cursor, str)
    with pytest.raises(RecoveryProgressRequestError, match="work_id"):
        read_recovery_progress(root, "feat_001", cursor=cursor)

    publish_committed_transition(root, _receipt(99), {})
    with pytest.raises(RecoveryProgressRevisionChanged) as changed:
        read_recovery_progress(root, "task_001", cursor=cursor)
    assert changed.value.to_dict()["error"]["code"] == "revision_changed"


def test_missing_stale_wrong_root_and_symlink_are_explicit_pending(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    missing = read_recovery_progress(root, "task_001")
    assert missing["error"]["code"] == "evidence_missing"

    _publish(root, 1)
    stale = read_recovery_progress(
        root,
        "task_001",
        now=datetime(2100, 1, 1, tzinfo=timezone.utc),
    )
    assert stale["error"]["code"] == "evidence_stale"

    work = (
        root
        / ".cascade/recovery_progress/v1/work"
        / __import__("hashlib").sha256(b"task_001").hexdigest()
    )
    pointer = json.loads((work / "current.json").read_text())
    manifest_path = work / pointer["manifest"]
    manifest = json.loads(manifest_path.read_text())
    manifest["repository_identity"]["product"] = "another-root"
    manifest_path.write_text(json.dumps(manifest))
    wrong = read_recovery_progress(root, "task_001")
    assert wrong["error"]["code"] == "wrong_root"

    pointer_path = work / "current.json"
    actual = work / "pointer-target.json"
    actual.write_bytes(pointer_path.read_bytes())
    pointer_path.unlink()
    pointer_path.symlink_to(actual.name)
    unavailable = read_recovery_progress(root, "task_001")
    assert unavailable["error"]["code"] == "evidence_unavailable"


def test_board_summary_uses_the_same_primary_and_additive_identity(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    _publish(root, 2)
    progress = read_recovery_progress(root, "task_001", limit=1)
    incident, metadata = board_recovery_projection(progress)
    assert incident is not None
    assert incident["target"]["id"] == progress["primary"]["action_id"]
    assert metadata == incident["recovery_progress"]
    assert metadata["revision"] == progress["revision"]
    assert metadata["entry_id"] == progress["primary"]["entry_id"]
    assert metadata["count"] == 2
    assert metadata["next_cursor"]
    assert metadata["primary"]["entry_id"] == progress["primary"]["entry_id"]
    assert metadata["primary"]["receipt_ref_count"] == 1
    assert metadata["primary"]["milestone_ref_count"] == 0


def test_reader_has_no_read_side_effects(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _publish(root, 2)
    base = root / ".cascade/recovery_progress/v1"
    before = {
        path.relative_to(base): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in base.rglob("*")
        if path.is_file()
    }
    read_recovery_progress(root, "task_001")
    after = {
        path.relative_to(base): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in base.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_split_product_and_tracking_identity_is_exact(tmp_path: Path) -> None:
    product = make_repo(tmp_path / "product", git=False)
    tracking = make_repo(tmp_path / "tracking", git=False)
    set_project_context(ProjectContext.split(product, tracking))
    try:
        _publish(product, 1)
        result = read_recovery_progress(product, "task_001")
        assert result["primary"]["action_id"] == "task_001:recovery:000"

        set_project_context(ProjectContext.colocated(product))
        wrong = read_recovery_progress(product, "task_001")
        assert wrong["error"]["code"] == "wrong_root"
    finally:
        set_project_context(None)


def test_epic_044_api_fixture_freezes_the_shared_contract() -> None:
    fixture = json.loads(
        (
            Path(__file__).with_name("fixtures") / "recovery_progress_v1_epic_044.json"
        ).read_text()
    )
    assert set(fixture) == {
        "schema_version",
        "work_id",
        "revision",
        "observed_at",
        "expires_at",
        "completeness",
        "lag",
        "primary",
        "items",
        "entry_count",
        "next_cursor",
    }
    assert fixture["work_id"] == "epic_044"
    assert fixture["primary"]["state"] == "waiting_blocked"
    assert fixture["primary"]["receipt_refs"] == ["sha256:epic044-waiting-receipt"]
    assert fixture["items"] == [fixture["primary"]]
