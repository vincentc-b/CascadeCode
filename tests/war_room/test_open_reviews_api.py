"""Open-reviews registry read API integration coverage (feat_003 / task_007, task_008)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
import urllib.error
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Iterator

import pytest

from cascade.war_room.server import serve
from cascade.war_room.human_auth import LocalHumanIdentityVerifier, SESSION_COOKIE
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


def _post_json(url: str, payload: dict, *, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Cookie"] = f"{SESSION_COOKIE}={token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        response = urllib.request.urlopen(request)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    with response:
        return response.status, json.loads(response.read().decode())


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


def test_open_review_projects_exact_repair_identity(war_room_server):
    base, root = war_room_server
    reviews = _representative_registry()
    reviews["feat_001"].update(
        source_head="a" * 40,
        target_head="b" * 40,
        current_generation=7,
    )
    _write_reviews(root, reviews)

    _status, payload = _get_json(f"{base}/api/open-reviews")
    row = {item["id"]: item for item in payload["reviews"]}["feat_001"]

    assert row["repair_identity"] == {
        "review_url": "https://github.example/o/r/pull/1",
        "review_forge": "github",
        "source_ref": "feat/feat_001",
        "target_ref": "epic/epic_001",
        "observed_source_head": "a" * 40,
        "observed_target_head": "b" * 40,
        "observed_review_generation": 7,
    }


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
        "omitted": 0,
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


def test_open_reviews_preserve_distinct_names_and_report_omitted_rows(
    war_room_server,
):
    base, root = war_room_server
    names = [f"check-{index:02d}" for index in range(18)] + [
        "same-prefix-A",
        "same-prefix-B",
        "tail-20",
        "tail-21",
    ]
    checks = {name: {"status": "success", "generation": 0} for name in names}
    assert record_feature_review_evidence(
        "feat_001",
        {
            "review_health": {"state": "green", "checks": names},
            "required_check_policy": {"available": True, "required": names},
            "required_check_results": {
                "available": True,
                "generation": "🧪" * 64,
                "statuses": {name: "success" for name in names},
                "checks": checks,
            },
            "review_feedback": {"available": True, "actionable": False},
        },
        root=root,
    )

    _status, payload = _get_json(f"{base}/api/open-reviews")
    evidence = {item["id"]: item for item in payload["reviews"]}["feat_001"]["evidence"]
    projected_names = [row["name"] for row in evidence["ci"]["checks"]]
    assert len(projected_names) == 20
    assert "same-prefix-A" in projected_names
    assert "same-prefix-B" in projected_names
    assert evidence["ci"]["truncated"] is True
    assert evidence["ci"]["omitted"] == 2
    assert len(json.dumps(evidence, ensure_ascii=False).encode("utf-8")) < 32 * 1024


def test_open_reviews_preserve_scalar_boundaries_and_refuse_unicode_overflow(
    war_room_server,
):
    base, root = war_room_server

    for generation in (0, "🧪" * 64, int("9" * 64)):
        reviews = _representative_registry()
        reviews["feat_001"].update(
            review_health={"state": "green", "checks": ["🧪" * 64]},
            required_check_policy={
                "available": True,
                "required": ["🧪" * 64],
            },
            required_check_results={
                "available": True,
                "statuses": {"🧪" * 64: "success"},
                "checks": {
                    "🧪" * 64: {
                        "status": "success",
                        "generation": generation,
                    }
                },
            },
            review_feedback={"available": True},
            review_observed_at="2026-11-27T12:00:00+00:00",
        )
        _write_reviews(root, reviews)

        _status, payload = _get_json(f"{base}/api/open-reviews")
        evidence = {row["id"]: row for row in payload["reviews"]}["feat_001"][
            "evidence"
        ]
        assert evidence["health_state"] == "green"
        assert evidence["ci"]["checks"] == [
            {
                "name": "🧪" * 64,
                "status": "success",
                "generation": generation,
                "observed_at": None,
            }
        ]

    reviews = _representative_registry()
    reviews["feat_001"].update(
        review_health={"state": "green", "checks": ["🧪" * 64 + "x"]},
        required_check_policy={
            "available": True,
            "required": ["🧪" * 64 + "x"],
        },
        required_check_results={
            "available": True,
            "statuses": {"🧪" * 64 + "x": "success"},
            "checks": {
                "🧪" * 64 + "x": {"status": "success", "generation": 0}
            },
        },
        review_feedback={"available": True},
        review_observed_at="2026-11-27T12:00:00+00:00",
    )
    _write_reviews(root, reviews)

    _status, payload = _get_json(f"{base}/api/open-reviews")
    open_row = {row["id"]: row for row in payload["reviews"]}["feat_001"]
    _status, board = _get_json(f"{base}/api/board")
    board_row = next(
        item
        for column in board["features"].values()
        for item in column
        if item["id"] == "feat_001"
    )
    _status, room = _get_json(f"{base}/api/doc/feat_001")

    assert open_row["evidence"] == board_row["review"]["evidence"]
    assert open_row["evidence"] == room["meta"]["review"]["evidence"]
    assert open_row["evidence"]["health_state"] == "unavailable"
    assert open_row["evidence"]["freshness"] == "unknown"
    assert open_row["next_prerequisite"] == "refresh_review_observation"


@pytest.mark.parametrize(
    "generation",
    ["🧪" * 64 + "x", int("9" * 65)],
)
def test_open_reviews_refuse_over_limit_string_and_integer_generations(
    war_room_server, generation
):
    base, root = war_room_server
    reviews = _representative_registry()
    reviews["feat_001"].update(
        review_health={"state": "green", "checks": ["build"]},
        required_check_policy={"available": True, "required": ["build"]},
        required_check_results={
            "available": True,
            "statuses": {"build": "success"},
            "checks": {"build": {"status": "success", "generation": generation}},
        },
        review_feedback={"available": True},
        review_observed_at="2026-11-27T12:00:00+00:00",
    )
    _write_reviews(root, reviews)

    _status, payload = _get_json(f"{base}/api/open-reviews")
    row = {item["id"]: item for item in payload["reviews"]}["feat_001"]
    assert row["evidence"]["health_state"] == "unavailable"
    assert row["next_prerequisite"] == "refresh_review_observation"


def test_open_reviews_refuse_oversized_legacy_observation_payload(
    war_room_server,
):
    base, root = war_room_server
    reviews = _representative_registry()
    reviews["feat_001"].update(
        review_health={"state": "green", "checks": ["build"]},
        required_check_policy={"available": True, "required": ["build"]},
        required_check_results={
            "available": True,
            "statuses": {"build": "success"},
            "checks": {"build": {"status": "success", "generation": 0}},
            "legacy_detail": "x" * (32 * 1024),
        },
        review_feedback={"available": True},
        review_observed_at="2026-11-27T12:00:00+00:00",
    )
    _write_reviews(root, reviews)

    _status, payload = _get_json(f"{base}/api/open-reviews")
    row = {item["id"]: item for item in payload["reviews"]}["feat_001"]
    assert row["evidence"]["health_state"] == "unavailable"
    assert row["evidence"]["ci"]["checks"] == []
    assert row["next_prerequisite"] == "refresh_review_observation"


@pytest.mark.parametrize("fallback", ["registry", "repair_request", "postcheck"])
def test_open_reviews_bound_oversized_legacy_and_repair_fallbacks(
    war_room_server, fallback
):
    base, root = war_room_server
    oversized = "🧪" * 65
    reviews = _representative_registry()
    if fallback == "registry":
        reviews["feat_001"].update(
            review_health={"state": "green"},
            required_check_policy={"available": True},
            required_check_results={
                "available": True,
                "checks": {"build": {"status": "success", "generation": oversized}},
            },
        )
        _write_reviews(root, reviews)
    else:
        action = {
            "kind": "feature_repair",
            "repair_route": "open_review",
            "action_id": f"feature_repair:feat_001:{fallback}",
            "request_id": fallback,
            "feature_id": "feat_001",
            "generation": 1,
            "phase": "verified" if fallback == "postcheck" else "delivery_pending",
        }
        checks = {"build": {"status": "success", "generation": oversized}}
        if fallback == "repair_request":
            action["request_evidence"] = {
                "review_health": {
                    "observation": {
                        "health_state": "green",
                        "blocker": {"checks": checks},
                    }
                }
            }
        else:
            action["verification_postcheck"] = {
                "verified": True,
                "required_check_results": {"available": True, "checks": checks},
            }
        _write_repair(root, action)

    _status, payload = _get_json(f"{base}/api/open-reviews")
    evidence = {item["id"]: item for item in payload["reviews"]}["feat_001"]["evidence"]
    assert evidence["health_state"] == "unavailable"
    assert evidence["health_reason"] == "review_evidence_out_of_bounds"
    assert evidence["ci"] == {
        "policy_status": "unavailable",
        "results_status": "unavailable",
        "checks": [],
        "truncated": False,
        "omitted": 0,
    }
    assert evidence["freshness"] == "unknown"
    assert evidence["next_prerequisite"] == "refresh_review_observation"
    row = {item["id"]: item for item in payload["reviews"]}["feat_001"]
    assert row["next_prerequisite"] == "refresh_review_observation"
    if fallback == "postcheck":
        assert row["repair"]["verified"] is False


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


def _repair_body() -> dict:
    return {
        "feature_id": "feat_001",
        "request_id": "review-fix:comment-7",
        "reason": "Address the scoped review finding",
        "evidence": {"comment_id": "comment-7"},
        "approval_reference": "authenticated-human:feat_001",
        "scope_reference": "review-comment:comment-7",
        "review_url": "https://github.example/o/r/pull/1",
        "review_forge": "github",
        "source_ref": "feat/feat_001",
        "target_ref": "epic/epic_001",
        "observed_source_head": "a" * 40,
        "observed_target_head": "b" * 40,
        "observed_review_generation": 3,
    }


def test_review_repair_post_authenticates_and_returns_adapter_result_unchanged(
    tmp_path, monkeypatch
):
    root = make_repo(tmp_path, git=False)
    _seed_board(root)
    _write_reviews(root, _representative_registry())
    observed = {}
    expected = {
        "ok": True,
        "feature_id": "feat_001",
        "admitted": True,
        "acknowledged": True,
        "wakeup_acknowledged": True,
        "executing": False,
        "executed": False,
        "refused": False,
        "verification_pending": True,
        "verified": False,
        "next_prerequisite": "feature_queue_checkpoint",
    }

    def request(feature_id, request_id, **kwargs):
        observed.update(feature_id=feature_id, request_id=request_id, **kwargs)
        return expected

    monkeypatch.setattr("cascade.war_room.review_routes.request_feature_review_repair", request)
    token = "review-action-token"
    port = _free_port()
    server = serve(
        root=root,
        host="127.0.0.1",
        port=port,
        human_identity_verifier=LocalHumanIdentityVerifier("local:operator", token),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _post_json(
            f"http://127.0.0.1:{port}/api/open-reviews/repair",
            _repair_body(),
            token=token,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.OK
    assert payload == expected
    assert observed["feature_id"] == "feat_001"
    assert observed["request_id"] == "review-fix:comment-7"
    assert observed["authenticated_human"].subject == "local:operator"
    assert observed["review_url"] == "https://github.example/o/r/pull/1"
    assert observed["observed_review_generation"] == 3


def test_review_repair_post_rejects_unauthenticated_and_changed_envelopes(
    tmp_path, monkeypatch
):
    root = make_repo(tmp_path, git=False)
    _seed_board(root)
    _write_reviews(root, _representative_registry())
    monkeypatch.setattr(
        "cascade.war_room.review_routes.request_feature_review_repair",
        lambda *_args, **_kwargs: pytest.fail("refused request must not reach adapter"),
    )
    token = "review-action-token"
    port = _free_port()
    server = serve(
        root=root,
        host="127.0.0.1",
        port=port,
        human_identity_verifier=LocalHumanIdentityVerifier("local:operator", token),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}/api/open-reviews/repair"
        status, _payload = _post_json(base, _repair_body())
        changed = _repair_body()
        changed["requesting_parent_id"] = "epic_001"
        changed_status, changed_payload = _post_json(base, changed, token=token)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.UNAUTHORIZED
    assert changed_status == HTTPStatus.BAD_REQUEST
    assert "unsupported review repair fields" in changed_payload["error"]
