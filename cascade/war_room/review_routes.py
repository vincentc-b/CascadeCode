"""War Room HTTP routes for the durable open-reviews registry (feat_003 / task_007)."""

from __future__ import annotations

from http import HTTPStatus
import json
import re
from typing import TYPE_CHECKING, Mapping

from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.review import list_open_reviews
from cascade.team_supervision import request_feature_review_repair
from cascade.war_room.serialize import open_review_to_dict

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler


_MAX_OPEN_REVIEW_ROWS = 100
REVIEW_REPAIR_PATH = "/api/open-reviews/repair"
_FEATURE_ID = re.compile(r"feat_[A-Za-z0-9][A-Za-z0-9_-]{0,119}\Z")
_REQUIRED_REPAIR_FIELDS = frozenset(
    {
        "feature_id",
        "request_id",
        "reason",
        "evidence",
        "approval_reference",
        "scope_reference",
        "review_url",
        "review_forge",
        "source_ref",
        "target_ref",
        "observed_source_head",
        "observed_target_head",
        "observed_review_generation",
    }
)
_OPTIONAL_REPAIR_FIELDS = frozenset(
    {"expected_generation", "claim_id", "claim_owner", "incident_budget_id"}
)


def register_review_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/open-reviews", handle_get_open_reviews)
    handler_cls.register_post_route(REVIEW_REPAIR_PATH, handle_post_review_repair)


def handle_get_open_reviews(handler: WarRoomRequestHandler) -> None:
    reviews = list_open_reviews(
        root=handler.server.root, limit=_MAX_OPEN_REVIEW_ROWS + 1
    )
    truncated = len(reviews) > _MAX_OPEN_REVIEW_ROWS
    payload = {
        "reviews": [
            open_review_to_dict(row) for row in reviews[:_MAX_OPEN_REVIEW_ROWS]
        ]
    }
    if truncated:
        payload["truncated"] = True
    handler._json_response(HTTPStatus.OK, payload)


def handle_post_review_repair(
    handler: WarRoomRequestHandler, body: dict[str, object]
) -> None:
    """Authenticate and delegate one exact open-review repair request."""

    human = _authenticated_human(handler)
    if human is None:
        return
    error = _validate_repair_body(body)
    if error is not None:
        handler._json_error(HTTPStatus.BAD_REQUEST, error)
        return
    feature_id = str(body["feature_id"])
    request_id = str(body["request_id"])
    request = {
        key: value
        for key, value in body.items()
        if key not in {"feature_id", "request_id"}
    }
    try:
        result = request_feature_review_repair(
            feature_id,
            request_id,
            root=handler.server.root,
            authenticated_human=human,
            **request,
        )
    except PermissionError as exc:
        handler._json_error(HTTPStatus.FORBIDDEN, str(exc))
        return
    except (OSError, ValueError) as exc:
        handler._json_response(
            HTTPStatus.CONFLICT,
            {
                "ok": False,
                "requested": True,
                "admitted": False,
                "acknowledged": False,
                "executing": False,
                "executed": False,
                "refused": True,
                "verified": False,
                "blocker": "repair_request_refused",
                "next_prerequisite": "refresh_repair_prerequisites",
                "error": str(exc),
            },
        )
        return
    handler._json_response(HTTPStatus.OK, result)


def _authenticated_human(
    handler: WarRoomRequestHandler,
) -> AuthenticatedHuman | None:
    verifier = handler.server.human_identity_verifier
    human = (
        verifier.verify_request(
            method=handler.command,
            path=handler.path.split("?", 1)[0],
            headers=handler.headers,
            client_address=handler.client_address,
        )
        if verifier is not None
        else None
    )
    if not isinstance(human, AuthenticatedHuman):
        handler._json_error(
            HTTPStatus.UNAUTHORIZED,
            "review repair requires an authenticated local human",
        )
        return None
    return human


def _validate_repair_body(body: Mapping[str, object]) -> str | None:
    fields = frozenset(body)
    missing = _REQUIRED_REPAIR_FIELDS - fields
    if missing:
        return "missing review repair fields: " + ", ".join(sorted(missing))
    extras = fields - _REQUIRED_REPAIR_FIELDS - _OPTIONAL_REPAIR_FIELDS
    if extras:
        return "unsupported review repair fields: " + ", ".join(sorted(extras))
    feature_id = body.get("feature_id")
    if not isinstance(feature_id, str) or _FEATURE_ID.fullmatch(feature_id) is None:
        return "feature_id must be a stable Feature identity"
    for field in (
        "request_id",
        "reason",
        "approval_reference",
        "scope_reference",
        "review_url",
        "review_forge",
        "source_ref",
        "target_ref",
        "observed_source_head",
        "observed_target_head",
    ):
        value = body.get(field)
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 2048
            or "\n" in value
            or "\r" in value
        ):
            return f"{field} must be a bounded nonempty single-line string"
    if not isinstance(body.get("evidence"), Mapping):
        return "evidence must be an object"
    evidence_size = len(
        json.dumps(body["evidence"], separators=(",", ":")).encode("utf-8")
    )
    if evidence_size > 65536:
        return "evidence exceeds 64 KiB"
    generation = body.get("observed_review_generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        return "observed_review_generation must be a nonnegative integer"
    expected = body.get("expected_generation")
    if expected is not None and (
        isinstance(expected, bool) or not isinstance(expected, int) or expected < 0
    ):
        return "expected_generation must be a nonnegative integer"
    for field in ("claim_id", "claim_owner", "incident_budget_id"):
        value = body.get(field)
        if value is not None and (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 256
            or "\n" in value
            or "\r" in value
        ):
            return f"{field} must be a bounded nonempty single-line string"
    return None
