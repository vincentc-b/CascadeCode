"""Open-reviews registry read API integration coverage (feat_003 / task_007, task_008)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Iterator

import pytest

from cascade.war_room.server import serve
from cascade.board.context import set_project_context
from cascade.review import record_feature_review_evidence
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get_json(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _write_reviews(root: Path, payload: dict) -> None:
    state_path = root / ".cascade" / "reviews.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_repair(root: Path, action: dict) -> None:
    state_path = root / ".cascade" / "executions.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"version": 3, "actions": {action["action_id"]: action}}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _seed_board(root: Path) -> None:
    add_doc(root, id="epic_001", title="Root epic", tier="epic")
    add_doc(root, id="epic_002", title="Other epic", tier="epic")
    add_doc(
        root,
        id="feat_001",
        title="Open feature",
        tier="feature",
        parent="epic_001",
        status="completed",
    )
    add_doc(
        root,
        id="feat_002",
        title="Closed feature",
        tier="feature",
        parent="epic_002",
        status="completed",
    )
    add_doc(
        root,
        id="feat_003",
        title="Merged feature",
        tier="feature",
        parent="epic_001",
        status="completed",
    )
    add_doc(
        root,
        id="feat_004",
        title="Second open feature",
        tier="feature",
        parent="epic_002",
        status="completed",
    )


def _representative_registry() -> dict:
    return {
        "feat_001": {
            "url": "https://github.example/o/r/pull/1",
            "number": "1",
            "forge": "github",
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "draft": False,
            "closed": False,
        },
        "feat_002": {
            "url": "https://github.example/o/r/pull/2",
            "number": "2",
            "forge": "github",
            "source_branch": "feat/feat_002",
            "target_branch": "epic/epic_002",
            "draft": False,
            "closed": True,
        },
        "feat_003": {
            "url": "https://github.example/o/r/pull/3",
            "number": "3",
            "forge": "github",
            "source_branch": "feat/feat_003",
            "target_branch": "epic/epic_001",
            "draft": False,
            "closed": True,
        },
        "feat_004": {
            "url": "https://github.example/o/r/pull/4",
            "number": "4",
            "forge": "github",
            "source_branch": "feat/feat_004",
            "target_branch": "epic/epic_002",
            "draft": False,
            "closed": False,
        },
    }


@contextmanager
def _war_room(root: Path, *, reviews: dict | None = None) -> Iterator[tuple[str, Path]]:
    _seed_board(root)
    _write_reviews(root, reviews if reviews is not None else _representative_registry())
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


@pytest.fixture
def war_room_server(tmp_path):
    root = make_repo(tmp_path, git=False)
    with _war_room(root) as pair:
        yield pair


def test_open_reviews_includes_open_registry_rows_and_excludes_closed(war_room_server):
    base, _root = war_room_server

    status, payload = _get_json(f"{base}/api/open-reviews")

    assert status == HTTPStatus.OK
    assert [row["id"] for row in payload["reviews"]] == ["feat_001", "feat_004"]
    assert "feat_002" not in {row["id"] for row in payload["reviews"]}
    assert "feat_003" not in {row["id"] for row in payload["reviews"]}


def test_open_reviews_response_carries_identifier_url_state_and_context(war_room_server):
    base, _root = war_room_server

    _status, payload = _get_json(f"{base}/api/open-reviews")

    by_id = {row["id"]: row for row in payload["reviews"]}
    row = by_id["feat_001"]
    assert row["url"] == "https://github.example/o/r/pull/1"
    assert row["original_review"] == {
        "url": "https://github.example/o/r/pull/1",
        "number": "1",
    }
    assert row["state"] == "awaiting_review"
    assert row["context"] == {
        "feature_id": "feat_001",
        "epic_id": "epic_001",
        "feature_title": "Open feature",
        "epic_title": "Root epic",
    }
    second = by_id["feat_004"]
    assert second["url"] == "https://github.example/o/r/pull/4"
    assert second["context"]["epic_id"] == "epic_002"
    assert second["context"]["epic_title"] == "Other epic"


def test_open_review_projects_delivery_unknown_evidence_and_legacy_generation(
    war_room_server,
):
    base, _root = war_room_server

    _status, payload = _get_json(f"{base}/api/open-reviews")
    row = {item["id"]: item for item in payload["reviews"]}["feat_001"]

    assert row["accountable_feature_id"] == "feat_001"
    assert row["accountable_epic_id"] == "epic_001"
    assert row["implementation_status"] == "completed"
    assert row["implementation_complete"] is True
    assert row["delivery_status"] == "review_pending"
    assert row["evidence"]["health_state"] == "unknown"
    assert row["evidence"]["ci"]["policy_status"] == "unknown"
    assert row["evidence"]["feedback"]["status"] == "unknown"
    assert row["evidence"]["freshness"] == "unknown"
    assert row["repair"]["generation"] == 0
    assert row["repair"]["requested"] is False
    assert row["next_prerequisite"] == "await_current_review_acceptance"


def test_open_reviews_preserve_pending_and_unavailable_persisted_health(
    war_room_server,
):
    base, root = war_room_server
    record_feature_review_evidence(
        "feat_001",
        {
            "review_health": {"state": "pending", "checks": ["build"]},
            "required_check_policy": {"available": True, "required": ["build"]},
            "required_check_results": {
                "available": True,
                "statuses": {"build": "pending"},
                "checks": {"build": {"status": "pending", "generation": 7}},
            },
            "review_feedback": {
                "available": True,
                "approval_state": "waiting",
                "actionable": False,
            },
        },
        root=root,
    )
    record_feature_review_evidence(
        "feat_004",
        {
            "review_health": {
                "state": "transient_outage",
                "reason": "required_check_policy_unavailable",
            },
            "required_check_policy": {"available": False, "error": "unavailable"},
            "required_check_results": {"available": False, "error": "unavailable"},
            "review_feedback": {"available": False, "error": "unavailable"},
        },
        root=root,
    )

    _status, payload = _get_json(f"{base}/api/open-reviews")
    rows = {item["id"]: item for item in payload["reviews"]}

    assert rows["feat_001"]["evidence"]["health_state"] == "pending"
    assert rows["feat_001"]["evidence"]["ci"]["checks"][0]["status"] == "pending"
    assert rows["feat_001"]["evidence"]["feedback"]["approval_state"] == "waiting"
    assert rows["feat_001"]["evidence"]["freshness"] == "current"
    assert rows["feat_004"]["evidence"]["health_state"] == "transient_outage"
    assert rows["feat_004"]["evidence"]["ci"]["policy_status"] == "unavailable"
    assert rows["feat_004"]["evidence"]["feedback"]["status"] == "unavailable"


def test_open_review_projects_canonical_repair_and_bounded_failed_check_evidence(
    war_room_server,
):
    base, root = war_room_server
    action = {
        "kind": "feature_repair",
        "repair_route": "open_review",
        "action_id": "feature_repair:feat_001:abc",
        "request_id": "review-health:failed-build",
        "feature_id": "feat_001",
        "epic_id": "epic_001",
        "generation": 2,
        "phase": "delivery_pending",
        "next_action": "deliver_reserved_task",
        "request_evidence": {
            "review_health": {
                "observed_at": "2026-11-27T12:00:00+00:00",
                "observation": {
                    "health_state": "failed",
                    "blocker": {
                        "policy": {"available": True},
                        "checks": {
                            "build": {
                                "status": "failure",
                                "generation": 41,
                                "observed_at": "2026-11-27T11:59:00+00:00",
                            }
                        },
                    },
                },
            }
        },
    }
    _write_repair(root, action)

    _status, payload = _get_json(f"{base}/api/open-reviews")
    row = {item["id"]: item for item in payload["reviews"]}["feat_001"]

    assert row["delivery_status"] == "repair_in_progress"
    assert row["evidence"]["source"] == "repair_request"
    assert row["evidence"]["health_state"] == "failed"
    assert row["evidence"]["freshness"] == "current"
    assert row["evidence"]["ci"] == {
        "policy_status": "available",
        "results_status": "available",
        "checks": [
            {
                "name": "build",
                "status": "failure",
                "generation": 41,
                "observed_at": "2026-11-27T11:59:00+00:00",
            }
        ],
        "truncated": False,
    }
    assert row["repair"] == {
        "request_id": "review-health:failed-build",
        "action_id": "feature_repair:feat_001:abc",
        "generation": 2,
        "phase": "delivery_pending",
        "requested": True,
        "admitted": True,
        "acknowledged": True,
        "executing": True,
        "verified": False,
        "waiting": False,
        "refused": False,
        "next_prerequisite": "deliver_reserved_task",
    }
    assert row["next_prerequisite"] == "deliver_reserved_task"

    _status, board = _get_json(f"{base}/api/board")
    board_row = next(
        item
        for column in board["features"].values()
        for item in column
        if item["id"] == "feat_001"
    )
    assert board_row["review"]["repair"]["generation"] == 2
    assert board_row["review"]["delivery_status"] == "repair_in_progress"

    _status, room = _get_json(f"{base}/api/doc/feat_001")
    assert room["meta"]["review"]["evidence"]["health_state"] == "failed"
    assert room["meta"]["review"]["next_prerequisite"] == "deliver_reserved_task"

    action.update(
        phase="verified",
        next_action=None,
        verified_at="2026-11-27T12:05:00+00:00",
        verification_postcheck={
            "verified": True,
            "required_check_policy": {"available": True, "required": ["build"]},
            "required_check_results": {
                "available": True,
                "checks": {"build": {"status": "success", "generation": 42}},
            },
        },
    )
    _write_repair(root, action)
    _status, verified_payload = _get_json(f"{base}/api/open-reviews")
    verified = {
        item["id"]: item for item in verified_payload["reviews"]
    }["feat_001"]
    assert verified["repair"]["verified"] is True
    assert verified["repair"]["executing"] is False
    assert verified["evidence"]["source"] == "verification_postcheck"
    assert verified["evidence"]["health_state"] == "green"


def test_open_reviews_read_does_not_mutate_or_invoke_forge_or_provider(
    war_room_server, monkeypatch
):
    base, root = war_room_server
    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda *_args, **_kwargs: pytest.fail("GET must not query forge authority"),
    )
    monkeypatch.setattr(
        "cascade.agent.discovery.inventory.get_provider_inventory",
        lambda *_args, **_kwargs: pytest.fail("GET must not discover a provider"),
    )
    state_path = root / ".cascade" / "reviews.json"
    action_path = root / ".cascade" / "executions.json"
    _write_repair(
        root,
        {
            "kind": "feature_repair",
            "repair_route": "open_review",
            "action_id": "feature_repair:feat_001:read-only",
            "request_id": "read-only",
            "feature_id": "feat_001",
            "generation": 1,
            "phase": "waiting",
            "next_action": "refresh_required_check_policy",
        },
    )
    before = state_path.read_text(encoding="utf-8")
    action_before = action_path.read_text(encoding="utf-8")

    _status, _payload = _get_json(f"{base}/api/open-reviews")
    _status, _payload = _get_json(f"{base}/api/open-reviews")

    assert state_path.read_text(encoding="utf-8") == before
    assert action_path.read_text(encoding="utf-8") == action_before


def test_open_reviews_returns_empty_list_when_registry_has_no_open_rows(tmp_path):
    root = make_repo(tmp_path, git=False)
    closed_only = {
        feature_id: {**record, "closed": True}
        for feature_id, record in _representative_registry().items()
    }
    with _war_room(root, reviews=closed_only) as (base, _root):
        status, payload = _get_json(f"{base}/api/open-reviews")

    assert status == HTTPStatus.OK
    assert payload == {"reviews": []}


def test_open_reviews_bounds_rows_and_marks_truncation(tmp_path):
    root = make_repo(tmp_path, git=False)
    reviews = {
        f"feat_{index:03d}": {
            "url": f"https://github.example/o/r/pull/{index}",
            "number": str(index),
            "forge": "github",
            "source_branch": f"feat/feat_{index:03d}",
            "target_branch": "epic/epic_001",
            "draft": False,
            "closed": False,
        }
        for index in range(105)
    }
    with _war_room(root, reviews=reviews) as (base, _root):
        status, payload = _get_json(f"{base}/api/open-reviews")

    assert status == HTTPStatus.OK
    assert len(payload["reviews"]) == 100
    assert payload["truncated"] is True


def test_open_reviews_joins_product_review_to_tracking_accountability(tmp_path):
    product = make_repo(tmp_path / "product", git=False)
    tracking = make_repo(tmp_path / "tracking", git=False)
    set_project_context(ProjectContext.split(product, tracking))
    try:
        _seed_board(tracking)
        _write_reviews(product, _representative_registry())
        port = _free_port()
        server = serve(root=product, host="127.0.0.1", port=port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            _status, payload = _get_json(
                f"http://127.0.0.1:{port}/api/open-reviews"
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    finally:
        set_project_context(None)

    row = {item["id"]: item for item in payload["reviews"]}["feat_001"]
    assert row["context"]["feature_title"] == "Open feature"
    assert row["context"]["epic_title"] == "Root epic"
    assert row["accountable_epic_id"] == "epic_001"
