"""Board rows only compute recovery controls for Tasks that can need them."""

from pathlib import Path

from cascade.war_room.serialize import work_meta_to_dict
from tests.support import add_doc, make_repo


def test_completed_task_board_row_skips_recovery_lookup(tmp_path: Path, monkeypatch) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    completed = add_doc(
        root, id="task_001", title="Done", tier="task", status="completed", parent="feat_001"
    )
    blocked = add_doc(
        root, id="task_002", title="Needs help", tier="task", status="blocked", parent="feat_001"
    )
    calls: list[str] = []

    def recovery_status(task_id: str, *, feature_id: str, root: Path) -> dict[str, str]:
        calls.append(task_id)
        return {"action": "retry"}

    monkeypatch.setattr("cascade.feature.recovery.recovery_status", recovery_status)

    done_row = work_meta_to_dict(completed.meta, root=root, sidecars_preloaded=True)
    blocked_row = work_meta_to_dict(blocked.meta, root=root, sidecars_preloaded=True)

    assert done_row["recovery"] is None
    assert blocked_row["recovery"] == {"action": "retry"}
    assert calls == ["task_002"]
