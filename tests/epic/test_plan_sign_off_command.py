"""Role-authorized epic plan sign-off command (task_015_001_002)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.comments.store import comment, resolve_comment
from cascade.epic.planning_signoffs import (
    InvalidPlanningRole,
    StalePlanRevision,
    UnauthorizedPlanningSignOff,
    UnresolvedOpenQuestions,
    canonical_plan_revision,
    current_valid_sign_offs,
    sign_off_epic_plan,
)
from tests.support import (
    EPIC_BODY,
    add_doc,
    approve_epic_plan_when_ready,
    commit_board,
    make_repo,
)


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Child",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    commit_board(root, "initial")
    return root


def _revision(board: Path) -> str:
    revision = canonical_plan_revision("epic_001", root=board)
    assert revision is not None
    return revision


def test_each_role_signs_for_current_revision(board: Path) -> None:
    revision = _revision(board)
    manager = sign_off_epic_plan(
        "epic_001", "epic_manager", revision, root=board, actor="epic_manager"
    )
    assert manager["newly_signed"] is True
    assert manager["sign_offs"] == {"epic_manager": manager["sign_offs"]["epic_manager"]}

    architect = sign_off_epic_plan(
        "epic_001", "epic_architect", revision, root=board, actor="epic_architect"
    )
    assert architect["newly_signed"] is True
    assert set(architect["sign_offs"]) == {"epic_manager", "epic_architect"}


def test_idempotent_repeat(board: Path) -> None:
    revision = _revision(board)
    first = sign_off_epic_plan(
        "epic_001", "epic_manager", revision, root=board, actor="epic_manager"
    )
    second = sign_off_epic_plan(
        "epic_001", "epic_manager", revision, root=board, actor="epic_manager"
    )
    assert first["newly_signed"] is True
    assert second["newly_signed"] is False
    assert len(current_valid_sign_offs("epic_001", root=board)) == 1


def test_agent_cannot_sign_for_other_role(board: Path) -> None:
    revision = _revision(board)
    with pytest.raises(UnauthorizedPlanningSignOff):
        sign_off_epic_plan(
            "epic_001",
            "epic_architect",
            revision,
            root=board,
            actor="epic_manager",
        )


def test_invalid_role_rejected(board: Path) -> None:
    revision = _revision(board)
    with pytest.raises(InvalidPlanningRole):
        sign_off_epic_plan("epic_001", "boss", revision, root=board)  # type: ignore[arg-type]


def test_stale_revision_rejected(board: Path) -> None:
    revision = _revision(board)
    with pytest.raises(StalePlanRevision):
        sign_off_epic_plan(
            "epic_001",
            "epic_manager",
            "0" * 40,
            root=board,
            actor="epic_manager",
        )
    assert current_valid_sign_offs("epic_001", root=board) == {}


def test_open_question_blocks_sign_off(board: Path) -> None:
    revision = _revision(board)
    comment(
        "epic_001",
        "Open questions",
        "Need scope decision",
        author="human",
        root=board,
    )
    with pytest.raises(UnresolvedOpenQuestions):
        sign_off_epic_plan(
            "epic_001",
            "epic_manager",
            revision,
            root=board,
            actor="epic_manager",
        )


def test_resolved_open_question_allows_sign_off(board: Path) -> None:
    revision = _revision(board)
    comment_id = comment(
        "epic_001",
        "Open questions",
        "Need scope decision",
        author="human",
        root=board,
    )
    resolve_comment("epic_001", comment_id, author="human", root=board)
    payload = sign_off_epic_plan(
        "epic_001",
        "epic_manager",
        revision,
        root=board,
        actor="epic_manager",
    )
    assert payload["newly_signed"] is True


def test_approved_epic_rejects_sign_off(board: Path) -> None:
    revision = _revision(board)
    approve_epic_plan_when_ready("epic_001", root=board)
    with pytest.raises(Exception, match="already approved"):
        sign_off_epic_plan("epic_001", "epic_manager", revision, root=board)


def test_sign_off_epic_plan_api(board: Path) -> None:
    from cascade.war_room.server import serve

    revision = _revision(board)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = serve(root=board, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/sign_off_epic_plan",
            method="POST",
            data=json.dumps(
                {
                    "id": "epic_001",
                    "role": "epic_manager",
                    "plan_revision": revision,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read().decode())
        assert resp.status == HTTPStatus.OK
        assert payload["newly_signed"] is True
        assert payload["role"] == "epic_manager"

        stale = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/sign_off_epic_plan",
            method="POST",
            data=json.dumps(
                {
                    "id": "epic_001",
                    "role": "epic_architect",
                    "plan_revision": "0" * 40,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(stale)
        assert exc.value.code == HTTPStatus.CONFLICT
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_material_revision_invalidates_stale_client(board: Path) -> None:
    revision_a = _revision(board)
    sign_off_epic_plan(
        "epic_001",
        "epic_manager",
        revision_a,
        root=board,
        actor="epic_manager",
    )

    from cascade.board.store import read_doc, write_doc

    epic = read_doc("epic_001", root=board)
    epic.body = EPIC_BODY.replace("None yet.", "Revised plan.")
    write_doc(epic, root=board)
    commit_board(board, "plan edit")
    revision_b = _revision(board)
    assert revision_b != revision_a

    with pytest.raises(StalePlanRevision):
        sign_off_epic_plan(
            "epic_001",
            "epic_architect",
            revision_a,
            root=board,
            actor="epic_architect",
        )
