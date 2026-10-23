"""Feature readiness on backlog feature rows from GET /api/board."""

from __future__ import annotations

import threading
from datetime import date
from http import HTTPStatus

import pytest

from cascade.board.parse import render_doc
from cascade.board.paths import column_dir, column_for_status, slugify
from cascade.board.types import WorkDoc, WorkMeta
from cascade.boss.view import compute_boss_view
from cascade.war_room.server import serve
from tests.support import FEATURE_BODY, add_doc, approve_board_feature, make_repo
from tests.war_room.test_http_read import _free_port, _get


def _feature_row(payload: dict, feature_id: str) -> dict:
    for column in ("1_backlog", "2_active", "3_completed"):
        for row in payload["features"][column]:
            if row["id"] == feature_id:
                return row
    raise KeyError(feature_id)


def _has_blocker(blockers: list[str], code: str) -> bool:
    prefix = code + ":"
    return any(item == code or item.startswith(prefix) for item in blockers)


def _write_parentless_feature(root, *, id: str, title: str) -> None:
    column = column_for_status("backlog")
    path = root / column_dir("feature", column) / f"{id}_{slugify(title)}.md"
    doc = WorkDoc(
        meta=WorkMeta(
            id=id,
            title=title,
            tier="feature",
            status="backlog",
            parent=None,
            children=[],
            depends_on=[],
            owners=["tester"],
            skills=[],
            parent_rev=None,
            created=date(2026, 10, 9),
            updated=date(2026, 10, 9),
            path=path,
        ),
        body=FEATURE_BODY,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_doc(doc), encoding="utf-8")


@pytest.fixture
def war_room_server(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Needs approval",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Dependency",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_003",
        title="Waiting on dep",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_002"],
    )
    add_doc(
        root,
        id="feat_004",
        title="Ready",
        tier="feature",
        parent="epic_001",
    )
    _write_parentless_feature(root, id="feat_005", title="No parent epic")
    approve_board_feature(root, "feat_003")
    approve_board_feature(root, "feat_004")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_board_serializes_backlog_feature_readiness(war_room_server) -> None:
    base, root, _server = war_room_server
    status, payload, _headers = _get(f"{base}/api/board")
    assert status == HTTPStatus.OK

    unapproved = _feature_row(payload, "feat_001")
    assert unapproved["readiness"]["approved"] is False
    assert _has_blocker(unapproved["readiness"]["blockers"], "not_approved")

    waiting = _feature_row(payload, "feat_003")
    assert waiting["readiness"]["approved"] is True
    assert _has_blocker(waiting["readiness"]["blockers"], "unmet_deps")
    assert any("feat_002" in item for item in waiting["readiness"]["blockers"])

    ready = _feature_row(payload, "feat_004")
    assert ready["readiness"]["approved"] is True
    assert ready["readiness"]["blockers"] == []

    orphan = _feature_row(payload, "feat_005")
    assert _has_blocker(orphan["readiness"]["blockers"], "epic_inactive")

    boss = compute_boss_view(root=root)
    assert "feat_004" in boss.dispatchable_features
    assert "feat_005" not in boss.dispatchable_features
