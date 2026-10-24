"""Activation-through-approval planning gate integration (task_015_001_004)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from cascade.approvals import epic_plan_approved
from cascade.board.store import read_doc, write_doc
from cascade.comments.store import comment, resolve_comment
from cascade.epic.planning_signoffs import canonical_plan_revision
from tests.support import (
    EPIC_BODY,
    add_doc,
    approve_epic_plan_when_ready,
    commit_board,
    make_repo,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(base: str, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(
        f"{base}{path}",
        method="POST",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post_conflict(base: str, path: str, payload: dict[str, Any]) -> int:
    req = urllib.request.Request(
        f"{base}{path}",
        method="POST",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    return exc.value.code


def _get_json(base: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{base}{path}") as resp:
        return json.loads(resp.read().decode())


def _epic_row(board_payload: dict[str, Any], epic_id: str) -> dict[str, Any]:
    for column in ("1_backlog", "2_active", "3_completed"):
        for row in board_payload["epics"][column]:
            if row["id"] == epic_id:
                return row
    raise KeyError(epic_id)


def _readiness_from_api(base: str, epic_id: str) -> dict[str, Any]:
    board = _get_json(base, "/api/board")
    row = _epic_row(board, epic_id)
    doc = _get_json(base, f"/api/doc/{epic_id}")
    readiness = row["plan_readiness"]
    assert doc["plan_readiness"] == readiness
    return readiness


def _sign_off_api(
    base: str,
    *,
    epic_id: str,
    role: str,
    plan_revision: str,
) -> dict[str, Any]:
    status, body = _post(
        base,
        "/api/sign_off_epic_plan",
        {"id": epic_id, "role": role, "plan_revision": plan_revision},
    )
    assert status == HTTPStatus.OK
    return body


def _assert_readiness(
    base: str,
    epic_id: str,
    *,
    status: str,
    can_approve: bool,
    disabled_reason: str | None,
    signed_roles: set[str] | None = None,
) -> str | None:
    readiness = _readiness_from_api(base, epic_id)
    assert readiness["status"] == status
    assert readiness["can_approve_plan"] is can_approve
    assert readiness["approve_disabled_reason"] == disabled_reason
    if signed_roles is not None:
        assert set(readiness["sign_offs"]) == signed_roles
    revision = readiness.get("plan_revision")
    return revision if isinstance(revision, str) else None


@pytest.fixture
def planning_board(tmp_path: Path) -> tuple[Path, str]:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Flow epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Child",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    add_doc(root, id="epic_002", title="Already approved", tier="epic", status="active")
    add_doc(
        root,
        id="feat_002",
        title="Legacy child",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    commit_board(root, "initial")
    approve_epic_plan_when_ready("epic_002", root=root)
    assert epic_plan_approved("epic_002", root=root)

    port = _free_port()
    from cascade.war_room.server import serve

    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield root, base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# Each row is executed in order within one end-to-end activation-to-approval flow.
READINESS_EXPECTATIONS: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "after_activation",
        {
            "status": "planning",
            "can_approve": False,
            "disabled_reason": "missing_epic_manager_sign_off",
            "signed_roles": set(),
        },
    ),
    (
        "manager_signed",
        {
            "status": "planning",
            "can_approve": False,
            "disabled_reason": "missing_epic_architect_sign_off",
            "signed_roles": {"epic_manager"},
        },
    ),
    (
        "open_question_blocks",
        {
            "status": "planning",
            "can_approve": False,
            "disabled_reason": "unresolved_open_questions",
            "signed_roles": {"epic_manager"},
        },
    ),
    (
        "both_roles_signed",
        {
            "status": "ready_for_review",
            "can_approve": True,
            "disabled_reason": None,
            "signed_roles": {"epic_manager", "epic_architect"},
        },
    ),
    (
        "material_revision",
        {
            "status": "planning",
            "can_approve": False,
            "disabled_reason": "missing_epic_manager_sign_off",
            "signed_roles": set(),
        },
    ),
    (
        "re_signed_after_revision",
        {
            "status": "ready_for_review",
            "can_approve": True,
            "disabled_reason": None,
            "signed_roles": {"epic_manager", "epic_architect"},
        },
    ),
)


def test_activation_to_approval_planning_gate_flow(planning_board: tuple[Path, str]) -> None:
    root, base = planning_board
    epic_id = "epic_001"

    status, body = _post(base, "/api/activate_epic", {"id": epic_id, "by": "human"})
    assert status == HTTPStatus.OK
    assert body["ok"] is True
    assert read_doc(epic_id, root=root).meta.status == "active"

    assert _post_conflict(base, "/api/approve_epic_plan", {"id": epic_id}) == HTTPStatus.CONFLICT

    revision_a = _assert_readiness(
        base,
        epic_id,
        **_expectation_kwargs(READINESS_EXPECTATIONS[0]),
    )
    assert revision_a is not None

    _sign_off_api(
        base,
        epic_id=epic_id,
        role="epic_manager",
        plan_revision=revision_a,
    )
    assert _post_conflict(base, "/api/approve_epic_plan", {"id": epic_id}) == HTTPStatus.CONFLICT
    revision_a = _assert_readiness(
        base,
        epic_id,
        **_expectation_kwargs(READINESS_EXPECTATIONS[1]),
    )
    assert revision_a is not None

    comment_id = comment(
        epic_id,
        "Open questions",
        "Scope?",
        author="human",
        root=root,
    )
    assert (
        _post_conflict(
            base,
            "/api/sign_off_epic_plan",
            {
                "id": epic_id,
                "role": "epic_architect",
                "plan_revision": revision_a,
            },
        )
        == HTTPStatus.CONFLICT
    )
    _assert_readiness(
        base,
        epic_id,
        **_expectation_kwargs(READINESS_EXPECTATIONS[2]),
    )

    resolve_comment(epic_id, comment_id, author="human", root=root)
    _sign_off_api(
        base,
        epic_id=epic_id,
        role="epic_architect",
        plan_revision=revision_a,
    )
    revision_a = _assert_readiness(
        base,
        epic_id,
        **_expectation_kwargs(READINESS_EXPECTATIONS[3]),
    )
    assert revision_a is not None

    epic = read_doc(epic_id, root=root)
    epic.body = EPIC_BODY.replace("None yet.", "Revised scope.")
    write_doc(epic, root=root)
    commit_board(root, "plan revision")
    revision_b = canonical_plan_revision(epic_id, root=root)
    assert revision_b is not None and revision_b != revision_a

    assert _post_conflict(base, "/api/approve_epic_plan", {"id": epic_id}) == HTTPStatus.CONFLICT
    assert (
        _post_conflict(
            base,
            "/api/sign_off_epic_plan",
            {
                "id": epic_id,
                "role": "epic_architect",
                "plan_revision": revision_a,
            },
        )
        == HTTPStatus.CONFLICT
    )
    _assert_readiness(
        base,
        epic_id,
        **_expectation_kwargs(READINESS_EXPECTATIONS[4]),
    )

    _sign_off_api(
        base,
        epic_id=epic_id,
        role="epic_manager",
        plan_revision=revision_b,
    )
    _sign_off_api(
        base,
        epic_id=epic_id,
        role="epic_architect",
        plan_revision=revision_b,
    )
    _assert_readiness(
        base,
        epic_id,
        **_expectation_kwargs(READINESS_EXPECTATIONS[5]),
    )

    status, approve_body = _post(base, "/api/approve_epic_plan", {"id": epic_id})
    assert status == HTTPStatus.OK
    assert approve_body["features"] == ["feat_001"]
    assert epic_plan_approved(epic_id, root=root)

    board = _get_json(base, "/api/board")
    approved_row = _epic_row(board, epic_id)
    assert "plan_readiness" not in approved_row
    assert approved_row["plan_approved"] is True
    doc = _get_json(base, f"/api/doc/{epic_id}")
    assert "plan_readiness" not in doc

    assert epic_plan_approved("epic_002", root=root)
    legacy_row = _epic_row(board, "epic_002")
    assert "plan_readiness" not in legacy_row
    assert legacy_row["plan_approved"] is True


def _expectation_kwargs(row: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    _label, expected = row
    return {
        "status": expected["status"],
        "can_approve": expected["can_approve"],
        "disabled_reason": expected["disabled_reason"],
        "signed_roles": expected["signed_roles"],
    }
