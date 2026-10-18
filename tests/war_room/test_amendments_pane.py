"""War Room amendment pane HTTP API (task_029).

Manual check: run ``python3 -m cascade.war_room`` against a repo with an active
Feature, call ``propose_epic_amendment`` from the feature harness, confirm a
``kind: amendment`` toast appears, the pane lists the pending sidecar, the split
diff loads, and Accept updates the board/epic view after refresh.
"""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

import cascade.epic.amendments  # noqa: F401 — registers resolve tool
from cascade.amendments import extract_section_body, read_amendment
from cascade.board.store import pin_parent, read_doc, write_doc
from cascade.feature.amendments import ack_amendment, propose_epic_amendment
from cascade.war_room.server import serve
from tests.support import EPIC_BODY, add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(url: str) -> tuple[int, object, dict[str, str]]:
    with urllib.request.urlopen(url) as resp:
        raw = resp.read()
        headers = dict(resp.headers)
        ctype = resp.headers.get_content_type()
        if ctype == "application/json":
            return resp.status, json.loads(raw.decode()), headers
        return resp.status, raw.decode(), headers


def _get_expect_error(url: str) -> tuple[int, dict]:
    try:
        _get(url)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


def _post(url: str, payload: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post_expect_error(url: str, payload: dict | None = None) -> tuple[int, dict]:
    try:
        _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


@pytest.fixture
def amendment_board(tmp_path: Path) -> tuple[str, Path]:
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
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _propose(root: Path) -> str:
    return propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "Feature-owned write paths only.",
        "Need tighter isolation.",
        feature_id="feat_001",
        root=root,
    )


def test_list_pending_and_diff(amendment_board: tuple[str, Path]) -> None:
    base, root = amendment_board
    amd_id = _propose(root)

    status, rows, _ = _get(f"{base}/api/amendments?epic_id=epic_001")
    assert status == HTTPStatus.OK
    assert isinstance(rows, list)
    assert len(rows) == 1
    row = rows[0]
    assert row["amd_id"] == amd_id
    assert row["feature_id"] == "feat_001"
    assert row["section"] == "Cross-module constraints"
    assert row["state"] == "pending"
    assert "diff_path" in row
    assert "rationale_summary" in row

    status, diff_text, headers = _get(f"{base}/api/amendments/{amd_id}/diff")
    assert status == HTTPStatus.OK
    assert "text/plain" in headers.get("Content-type", headers.get("Content-Type", ""))
    assert "Cross-module constraints" in diff_text or "Feature-owned" in diff_text

    code, err = _get_expect_error(f"{base}/api/amendments/amd_999/diff")
    assert code == HTTPStatus.NOT_FOUND
    assert "error" in err


def test_resolve_accept_via_http(amendment_board: tuple[str, Path]) -> None:
    base, root = amendment_board
    amd_id = _propose(root)

    status, body = _post(
        f"{base}/api/amendments/{amd_id}/resolve",
        {"decision": "accept"},
    )
    assert status == HTTPStatus.OK
    epic_rev = body["epic_rev"]
    assert isinstance(epic_rev, str) and len(epic_rev) == 40

    epic = read_doc("epic_001", root=root)
    section = extract_section_body(epic.body, "Cross-module constraints")
    assert section.strip() == "Feature-owned write paths only."
    assert read_amendment(amd_id, root=root).state == "accepted"

    status, rows, _ = _get(f"{base}/api/amendments?epic_id=epic_001")
    assert rows == []


def test_resolve_reject_via_http(amendment_board: tuple[str, Path]) -> None:
    base, root = amendment_board
    amd_id = _propose(root)
    epic_before = read_doc("epic_001", root=root).body

    status, body = _post(
        f"{base}/api/amendments/{amd_id}/resolve",
        {"decision": "reject", "note": "Not needed."},
    )
    assert status == HTTPStatus.OK
    assert body["epic_rev"] is None
    assert read_doc("epic_001", root=root).body == epic_before
    assert read_amendment(amd_id, root=root).state == "rejected"


def test_resolve_revise_via_http(amendment_board: tuple[str, Path]) -> None:
    base, root = amendment_board
    amd_id = _propose(root)

    status, body = _post(
        f"{base}/api/amendments/{amd_id}/resolve",
        {
            "decision": "revise",
            "revised_text": "Counter-proposed constraints.",
            "note": "Try this wording.",
        },
    )
    assert status == HTTPStatus.OK
    assert body["epic_rev"] is None

    record = read_amendment(amd_id, root=root)
    assert record.state == "revise_pending"
    assert record.revised_text == "Counter-proposed constraints."

    status, rows, _ = _get(f"{base}/api/amendments?epic_id=epic_001")
    assert len(rows) == 1
    assert rows[0]["state"] == "revise_pending"

    ack_amendment(amd_id, feature_id="feat_001", root=root)
    status, body = _post(
        f"{base}/api/amendments/{amd_id}/resolve",
        {"decision": "accept"},
    )
    assert status == HTTPStatus.OK
    assert body["epic_rev"] is not None


def test_diff_route_accepts_amd_id_with_four_digits(
    amendment_board: tuple[str, Path],
) -> None:
    from datetime import datetime, timezone
    from pathlib import Path

    from cascade.amendments import Amendment, write_sidecar

    base, root = amendment_board
    epic = read_doc("epic_001", root=root)
    record = write_sidecar(
        Amendment(
            id="amd_1000",
            feature_id="feat_001",
            epic_id="epic_001",
            section="Cross-module constraints",
            diff_path=Path("."),
            proposed_text="Four-digit id.",
            rationale="Test.",
            state="pending",
            created=datetime.now(timezone.utc),
        ),
        epic.body,
        root=root,
    )
    assert record.id == "amd_1000"

    status, diff_text, _ = _get(f"{base}/api/amendments/amd_1000/diff")
    assert status == HTTPStatus.OK
    assert "Four-digit id" in diff_text or "Cross-module" in diff_text


def test_list_requires_epic_id(amendment_board: tuple[str, Path]) -> None:
    base, _root = amendment_board
    code, err = _get_expect_error(f"{base}/api/amendments")
    assert code == HTTPStatus.BAD_REQUEST
    assert err["error"] == "missing epic_id"
