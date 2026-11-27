"""Feature and epic approval persistence and API."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.approvals import (
    approve_epic_plan,
    approve_feature,
    epic_plan_approved,
    feature_approved,
)
from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.board.errors import BoardError, GitError
from cascade.board.store import read_doc, write_doc
from cascade.watchdog import activate_epic, dispatch_feature
from cascade.watchdog.events import read_events
from cascade.workspace.integration_worktree import integration_worktree_path
from tests.support import add_doc, approve_epic_plan_when_ready, commit_board, make_repo


@pytest.fixture(autouse=True)
def supported_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    now = time.time()
    inventory = ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(DiscoveredModel(id="offered", display_name="Offered"),),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, now, now + 300, 300),
    )
    monkeypatch.setattr("cascade.approvals.get_provider_inventory", lambda: inventory)
    monkeypatch.setattr("cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory)


def _select_supported(root: Path, work_id: str) -> None:
    doc = read_doc(work_id, root=root)
    roles = {
        "epic": ("epic_manager", "epic_architect", "feature_lead", "feature_architect", "swe"),
        "feature": ("feature_lead", "feature_architect", "swe"),
    }[doc.meta.tier]
    doc.meta.provider = "codex"
    doc.meta.models = {role: "offered" for role in roles}
    write_doc(doc, root=root)


def test_missing_approval_is_unapproved(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    doc = read_doc("feat_001", root=root)
    assert doc.meta.approved_at is None
    assert feature_approved("feat_001", root=root) is False


def test_approve_feature_persists_and_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_supported(root, "feat_001")

    first = approve_feature("feat_001", root=root)
    assert first["newly_approved"] is True
    approved_at = read_doc("feat_001", root=root).meta.approved_at
    assert isinstance(approved_at, datetime)

    second = approve_feature("feat_001", root=root)
    assert second["newly_approved"] is False
    assert read_doc("feat_001", root=root).meta.approved_at == approved_at


def test_concurrent_feature_approval_commits_one_current_receipt(tmp_path: Path) -> None:
    from cascade.feature.readiness_evidence import approval_evidence

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_supported(root, "feat_001")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _item: approve_feature("feat_001", root=root), range(2)))

    assert sorted(result["newly_approved"] for result in results) == [False, True]
    doc = read_doc("feat_001", root=root)
    assert approval_evidence(doc.meta, root=root)[0] == "current"


def test_dependency_declaration_is_revision_fenced_but_completion_is_not(
    tmp_path: Path,
) -> None:
    from cascade.feature.readiness_evidence import approval_evidence
    from cascade.board.store import move_doc

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="First", tier="feature", parent="epic_001")
    add_doc(root, id="feat_004", title="Fourth", tier="feature", parent="epic_001")
    add_doc(
        root,
        id="feat_002",
        title="Second",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_004", "feat_001"],
    )
    _select_supported(root, "feat_002")

    approve_feature("feat_002", root=root)
    owner = read_doc("feat_002", root=root)
    assert approval_evidence(owner.meta, root=root)[0] == "current"
    assert dispatch_feature("feat_002", "boss", root=root).reason == "dependency_unmet"

    owner.meta.depends_on.reverse()
    write_doc(owner, root=root)
    assert approval_evidence(owner.meta, root=root)[0] == "current"

    move_doc("feat_001", "completed", root=root)
    owner = read_doc("feat_002", root=root)
    assert approval_evidence(owner.meta, root=root)[0] == "current"

    add_doc(root, id="feat_003", title="Third", tier="feature", parent="epic_001")
    owner.meta.depends_on.append("feat_003")
    write_doc(owner, root=root)
    assert approval_evidence(owner.meta, root=root)[0] == "stale"


@pytest.mark.parametrize(
    ("mutation", "reason", "affected_ids"),
    [
        (
            "declaration",
            "dependency_declaration_changed",
            ("feat_001", "feat_002", "feat_003"),
        ),
        ("owner", "dependency_owner_changed", ("feat_001", "feat_002")),
    ],
)
def test_feature_approval_refuses_dependency_owner_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    reason: str,
    affected_ids: tuple[str, ...],
) -> None:
    from cascade.planning_action_dependencies import DependencyActionRefused

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="First", tier="feature", parent="epic_001")
    add_doc(root, id="feat_003", title="Third", tier="feature", parent="epic_001")
    add_doc(
        root,
        id="feat_002",
        title="Owner",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    _select_supported(root, "feat_002")

    def change_declaration(*_args: object, **_kwargs: object) -> None:
        doc = read_doc("feat_002", root=root)
        if mutation == "declaration":
            doc.meta.depends_on.append("feat_003")
        else:
            doc.meta.owners.append("replacement")
        write_doc(doc, root=root)

    monkeypatch.setattr(
        "cascade.lifecycle_review_gate.require_lifecycle_review_gate",
        change_declaration,
    )
    with pytest.raises(DependencyActionRefused) as refused:
        approve_feature("feat_002", root=root)

    assert refused.value.reasons == (reason,)
    assert refused.value.affected_work_ids == affected_ids
    assert read_doc("feat_002", root=root).meta.approved_at is None


def test_retry_repairs_interrupted_approval_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.feature import readiness_evidence

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_supported(root, "feat_001")
    real_write = readiness_evidence.write_approval_evidence
    calls = 0

    def interrupt_once(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("interrupted receipt write")
        real_write(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(readiness_evidence, "write_approval_evidence", interrupt_once)
    with pytest.raises(OSError, match="interrupted receipt write"):
        approve_feature("feat_001", root=root)
    interrupted = read_doc("feat_001", root=root)
    assert interrupted.meta.approved_at is not None
    assert readiness_evidence.approval_evidence(interrupted.meta, root=root)[0] == "unknown"

    assert approve_feature("feat_001", root=root)["newly_approved"] is True
    repaired = read_doc("feat_001", root=root)
    assert readiness_evidence.approval_evidence(repaired.meta, root=root)[0] == "current"


def test_epic_approval_snapshots_children_and_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="One", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Two", tier="feature", parent="epic_001")
    _select_supported(root, "feat_001")
    _select_supported(root, "feat_002")

    first = approve_epic_plan_when_ready("epic_001", root=root)
    assert first["features"] == ["feat_001", "feat_002"]
    assert epic_plan_approved("epic_001", root=root) is True
    assert feature_approved("feat_001", root=root) is True
    assert feature_approved("feat_002", root=root) is True
    plan_ts = read_doc("epic_001", root=root).meta.plan_approved_at
    events, _ = read_events("epic_001", 0, root=root)
    assert [event.type for event in events] == ["EpicPlanApproved"]

    second = approve_epic_plan("epic_001", root=root)
    assert second["features"] == ["feat_001", "feat_002"]
    assert read_doc("epic_001", root=root).meta.plan_approved_at == plan_ts
    events_again, _ = read_events("epic_001", 0, root=root)
    assert len(events_again) == 1


def test_child_added_after_epic_approval_stays_unapproved(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="One", tier="feature", parent="epic_001")
    _select_supported(root, "feat_001")
    approve_epic_plan_when_ready("epic_001", root=root)

    add_doc(root, id="feat_002", title="Later", tier="feature", parent="epic_001")

    assert feature_approved("feat_001", root=root) is True
    assert feature_approved("feat_002", root=root) is False


def test_epic_approval_commits_docs_in_their_owning_checkouts(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    (root / ".gitignore").write_text(".cascade/\n", encoding="utf-8")
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_supported(root, "epic_001")
    _select_supported(root, "feat_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    epic_root = integration_worktree_path("epic", "epic_001", trunk=root)
    trunk_before = _head(root)
    epic_before = _head(epic_root)

    approve_epic_plan_when_ready("epic_001", root=root)

    assert _head(root) != trunk_before
    assert _head(epic_root) != epic_before
    assert feature_approved("feat_001", root=root) is True
    assert epic_plan_approved("epic_001", root=root) is True
    assert _status(root, "docs/epics", "docs/features") == ""
    assert _status(epic_root, "docs/epics", "docs/features") == ""


def test_epic_approval_marks_plan_only_after_all_children_succeed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_supported(root, "feat_001")

    def fail_child(feature_id: str, *, root: Path) -> bool:
        raise RuntimeError(f"could not approve {feature_id}")

    monkeypatch.setattr("cascade.approvals._set_feature_approved", fail_child)

    from tests.support import sign_off_both_planning_roles

    sign_off_both_planning_roles("epic_001", root=root)
    with pytest.raises(RuntimeError, match="could not approve feat_001"):
        approve_epic_plan("epic_001", root=root)

    assert epic_plan_approved("epic_001", root=root) is False


def _head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _status(root: Path, *paths: str) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain", "--", *paths],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_approve_feature_enables_dispatch_when_automation_off(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_supported(root, "epic_001")
    _select_supported(root, "feat_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    refused = dispatch_feature("feat_001", "human", root=root)
    assert refused.reason == "not_approved"

    approve_feature("feat_001", root=root)
    doc = read_doc("feat_001", root=root)
    doc.body = doc.body.replace("## Scope", "## Scope\n\nChanged plan after approval.")
    write_doc(doc, root=root)
    assert dispatch_feature("feat_001", "human", root=root).reason == "not_approved"
    assert approve_feature("feat_001", root=root)["newly_approved"] is True
    started = dispatch_feature("feat_001", "human", root=root)
    assert started.ok is True


def test_approve_feature_api(tmp_path: Path) -> None:
    import socket
    import threading

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_supported(root, "feat_001")
    from cascade.war_room.server import serve

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = serve(root=root, host="127.0.0.1", port=port)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/approve_feature",
            method="POST",
            data=json.dumps({"id": "feat_001"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read().decode())
        assert resp.status == HTTPStatus.OK
        assert payload["newly_approved"] is True
        assert payload["approval_result"] == "approved"
        assert payload["approval_state"] == "approved"
        assert payload["execution_state"] == "waiting"
        assert payload["dispatch_pending"] is True
        assert payload["approval_explanation"]["code"] == "approval_saved_waiting"
        assert payload["affected_work_ids"] == ["feat_001", "epic_001"]
        assert feature_approved("feat_001", root=root) is True

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/board") as resp:
            board = json.loads(resp.read().decode())
        feature = board["features"]["1_backlog"][0]
        assert feature["id"] == "feat_001"
        assert feature["approved"] is True
        assert "approved_at" in feature
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_saved_approval_stays_successful_when_result_readback_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_supported(root, "feat_001")

    def fail_readback(*_args: object, **_kwargs: object) -> None:
        raise OSError("readback unavailable")

    monkeypatch.setattr(
        "cascade.approvals._add_feature_approval_contract", fail_readback
    )
    result = approve_feature("feat_001", root=root)

    assert result["ok"] is True
    assert result["newly_approved"] is True
    assert result["approval_result"] == "unknown"
    assert result["approval_state"] == "unknown"
    assert result["execution_state"] == "unknown"
    assert feature_approved("feat_001", root=root) is True


def test_approval_apis_return_conflict_for_board_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    import threading

    root = make_repo(tmp_path, git=False)
    from cascade.war_room.server import serve

    def fail_epic(*args: object, **kwargs: object) -> None:
        raise GitError("epic approval commit failed")

    def fail_feature(*args: object, **kwargs: object) -> None:
        raise BoardError("feature approval failed")

    monkeypatch.setattr("cascade.approvals.approve_epic_plan", fail_epic)
    monkeypatch.setattr("cascade.approvals.approve_feature", fail_feature)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        cases = (
            ("approve_epic_plan", "epic_001", "epic approval commit failed"),
            ("approve_feature", "feat_001", "feature approval failed"),
        )
        for endpoint, work_id, message in cases:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/{endpoint}",
                method="POST",
                data=json.dumps({"id": work_id}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)
            assert exc_info.value.code == HTTPStatus.CONFLICT
            payload = json.loads(exc_info.value.read().decode())
            assert payload["error"] == message
            if endpoint == "approve_feature":
                assert payload["approval_result"] == "refused"
                assert payload["approval_state"] == "unapproved"
                assert payload["execution_state"] == "unknown"
                assert payload["affected_work_ids"] == ["feat_001"]
                assert payload["approval_explanation"] == {
                    "code": "board_refused",
                    "message": message,
                }
            else:
                assert payload == {"error": message}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_approval_apis_can_finish_after_generic_request_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    import threading

    root = make_repo(tmp_path, git=False)
    from cascade.war_room.server import serve

    def slow_approval(*args: object, **kwargs: object) -> dict[str, bool]:
        time.sleep(0.1)
        return {"newly_approved": True}

    monkeypatch.setattr("cascade.approvals.approve_epic_plan", slow_approval)
    monkeypatch.setattr("cascade.approvals.approve_feature", slow_approval)
    monkeypatch.setattr("cascade.war_room.server.REQUEST_DEADLINE_S", 0.05)
    monkeypatch.setattr("cascade.war_room.server.APPROVAL_DEADLINE_S", 0.5)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for endpoint, work_id in (
            ("approve_epic_plan", "epic_001"),
            ("approve_feature", "feat_001"),
        ):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/{endpoint}",
                method="POST",
                data=json.dumps({"id": work_id}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                payload = json.loads(resp.read().decode())
            assert resp.status == HTTPStatus.OK
            assert payload == {"newly_approved": True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("bulk", [False, True])
def test_reapprove_changed_open_feature_refreshes_dispatch_evidence(
    tmp_path: Path, bulk: bool
) -> None:
    from cascade.boss.view import compute_boss_view
    from cascade.feature.readiness_evidence import approval_evidence

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _select_supported(root, "feat_001")
    approve_epic_plan_when_ready("epic_001", root=root)
    doc = read_doc("feat_001", root=root)
    old_timestamp = doc.meta.approved_at
    doc.body = doc.body.replace("## Scope", "## Scope\n\nChanged acceptance scope.")
    write_doc(doc, root=root)
    assert approval_evidence(doc.meta, root=root)[0] == "stale"
    assert "feat_001" not in compute_boss_view(root=root).dispatchable_features

    if bulk:
        approve_epic_plan("epic_001", root=root)
    else:
        assert approve_feature("feat_001", root=root)["newly_approved"] is True
    doc = read_doc("feat_001", root=root)
    assert doc.meta.approved_at > old_timestamp
    assert approval_evidence(doc.meta, root=root)[0] == "current"
    assert "feat_001" in compute_boss_view(root=root).dispatchable_features
    assert approve_feature("feat_001", root=root)["newly_approved"] is False
    assert read_doc("feat_001", root=root).meta.approved_at == doc.meta.approved_at
