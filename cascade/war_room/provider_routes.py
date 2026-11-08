"""War Room HTTP routes for provider status and credential store (task_075)."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from cascade.agent.credentials import forget_user_store_token, write_user_store_token
from cascade.agent.execution_preflight import provider_blocker
from cascade.agent.errors import ProviderConfigError
from cascade.agent.providers import parse_provider_id, probe_providers
from cascade.board.errors import BoardError, NotFound
from cascade.workspace.doc_root import read_doc_resolved
from cascade.provider_recovery import ProviderRecoveryRequest
from cascade.provider_recovery_command import (
    AuthenticatedHumanPrincipal,
    continue_without_flex_command,
    recover_active_item_provider_command,
)
from cascade.watchdog.config import read_providers_config
from cascade.war_room.serialize import providers_view_to_dict

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler

_TOKEN_SUFFIX = "/token"
_FORGET_SUFFIX = "/forget"
_RECOVERY_PREFIX = "/api/provider-recovery/"
_CONTINUE_ACTION = "continue-without-flex"


def register_provider_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/providers", handle_get_providers)


def handle_get_providers(handler: WarRoomRequestHandler) -> None:
    config = read_providers_config(handler.server.root)
    statuses = probe_providers()
    payload = providers_view_to_dict(config.default, statuses)
    handler._json_response(HTTPStatus.OK, payload)


def try_handle_provider_post(
    handler: WarRoomRequestHandler, body: dict[str, Any]
) -> bool:
    path = handler.path.split("?", 1)[0]
    if path.startswith(_RECOVERY_PREFIX):
        return _handle_recovery_post(handler, path, body)
    prefix = "/api/providers/"
    if not path.startswith(prefix):
        return False
    rest = path.removeprefix(prefix).strip("/")
    if rest.endswith(_TOKEN_SUFFIX):
        provider_raw = rest[: -len(_TOKEN_SUFFIX)].strip("/")
        if not provider_raw or "/" in provider_raw:
            handler._json_error(HTTPStatus.NOT_FOUND, "not found")
            return True
        return _handle_post_token(handler, provider_raw, body)
    if rest.endswith(_FORGET_SUFFIX):
        provider_raw = rest[: -len(_FORGET_SUFFIX)].strip("/")
        if not provider_raw or "/" in provider_raw:
            handler._json_error(HTTPStatus.NOT_FOUND, "not found")
            return True
        return _handle_post_forget(handler, provider_raw)
    handler._json_error(HTTPStatus.NOT_FOUND, "not found")
    return True


def _handle_recovery_post(
    handler: WarRoomRequestHandler, path: str, body: dict[str, Any]
) -> bool:
    """Run a human recovery action from the loopback War Room.

    This is intentionally not a general provider mutation endpoint.  The
    browser may only ask for a recovery on a currently blocked item; the
    command rechecks active state and lifecycle quiescence under its own lock.
    """

    parts = path.removeprefix(_RECOVERY_PREFIX).strip("/").split("/")
    if len(parts) != 2 or not parts[0] or parts[1] not in {
        "change",
        "retry",
        _CONTINUE_ACTION,
    }:
        handler._json_error(HTTPStatus.NOT_FOUND, "not found")
        return True
    work_id, action = parts
    if action == _CONTINUE_ACTION:
        return _handle_continue_without_flex(handler, work_id, body)
    try:
        doc = read_doc_resolved(work_id, root=handler.server.root)
        blocker = provider_blocker(work_id, root=handler.server.root)
    except (BoardError, NotFound, OSError, ValueError):
        handler._json_error(HTTPStatus.NOT_FOUND, "work item not found")
        return True
    if doc.meta.tier not in {"epic", "feature", "task"} or doc.meta.status != "active":
        _recovery_refusal(
            handler,
            work_id,
            "not_active",
            "Provider recovery is only available for active work.",
        )
        return True
    if blocker is None:
        _recovery_refusal(
            handler,
            work_id,
            "no_provider_blocker",
            "No active provider recovery is required.",
        )
        return True
    if action == "retry" and blocker.get("classification") != "transient":
        _recovery_refusal(
            handler,
            work_id,
            "selection_change_required",
            "Choose a supported provider or model before retrying.",
        )
        return True

    request = _recovery_request(handler, doc, body, retry=action == "retry")
    if request is None:
        return True
    # The server is loopback-only and this route is not callable by agents or
    # schedulers.  The command still owns the authorization and lifecycle
    # recheck, so a stale board row or concurrent click cannot mutate pins.
    result = recover_active_item_provider_command(
        work_id, request, actor="human", root=handler.server.root
    )
    if not result.ok:
        _recovery_refusal(
            handler,
            work_id,
            result.error_code or "recovery_failed",
            result.reason or "Provider recovery could not complete safely.",
            disposition=result.disposition,
        )
        return True
    # Selection recovery authorizes a future attempt but is not itself a
    # provider process start.  Keep the incident active until that start runs
    # a fresh successful execution check of the complete blocked scope.
    handler._json_response(HTTPStatus.OK, result.to_dict())
    return True


def _handle_continue_without_flex(
    handler: WarRoomRequestHandler, work_id: str, body: dict[str, Any]
) -> bool:
    """Authorize and replay one concrete failed action from an explicit click."""

    expected = {
        "failed_action_id",
        "expected_document_revision",
        "expected_selection_fingerprint",
    }
    if set(body) != expected or not all(
        isinstance(body.get(name), str)
        and bool(body[name])
        and body[name].strip() == body[name]
        for name in expected
    ):
        handler._json_error(
            HTTPStatus.BAD_REQUEST,
            "failed_action_id, expected_document_revision, and expected_selection_fingerprint are required",
        )
        return True

    # Identity is intentionally supplied by the loopback War Room server, not
    # accepted from browser JSON. Agent/scheduler callers cannot self-assert a
    # human principal at the command boundary.
    result = continue_without_flex_command(
        work_id,
        failed_action_id=body["failed_action_id"],
        expected_document_revision=body["expected_document_revision"],
        expected_selection_fingerprint=body["expected_selection_fingerprint"],
        principal=AuthenticatedHumanPrincipal("human:war-room"),
        actor="human",
        root=handler.server.root,
    )
    handler._json_response(
        HTTPStatus.OK if result.ok else HTTPStatus.CONFLICT,
        result.to_dict(),
    )
    return True


def _recovery_request(
    handler: WarRoomRequestHandler, doc: Any, body: dict[str, Any], *, retry: bool
) -> ProviderRecoveryRequest | None:
    if retry:
        if body:
            handler._json_error(
                HTTPStatus.BAD_REQUEST, "retry does not accept a provider selection"
            )
            return None
        provider, models = doc.meta.provider, doc.meta.models
        reasoning, flex_mode = doc.meta.reasoning, doc.meta.flex_mode
    else:
        provider, models = body.get("provider"), body.get("models")
        reasoning, flex_mode = body.get("reasoning"), body.get("flex_mode")
    if not isinstance(provider, str) or not provider.strip():
        handler._json_error(HTTPStatus.BAD_REQUEST, "provider must be non-blank")
        return None
    if not isinstance(models, dict) or not all(
        isinstance(role, str) and isinstance(model, str) and model.strip()
        for role, model in models.items()
    ):
        handler._json_error(
            HTTPStatus.BAD_REQUEST, "models must map roles to non-blank model IDs"
        )
        return None
    if reasoning is not None and (
        not isinstance(reasoning, dict)
        or not all(
            isinstance(role, str) and (value is None or isinstance(value, str))
            for role, value in reasoning.items()
        )
    ):
        handler._json_error(
            HTTPStatus.BAD_REQUEST, "reasoning must map roles to strings or null"
        )
        return None
    if flex_mode is not None and not isinstance(flex_mode, bool):
        handler._json_error(
            HTTPStatus.BAD_REQUEST, "flex_mode must be a boolean or null"
        )
        return None
    return ProviderRecoveryRequest(
        provider.strip(), models, reasoning=reasoning, flex_mode=flex_mode
    )


def _recovery_refusal(
    handler: WarRoomRequestHandler,
    work_id: str,
    error_code: str,
    reason: str,
    *,
    disposition: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "ok": False,
        "work_id": work_id,
        "error_code": error_code,
        "reason": reason,
    }
    if disposition is not None:
        payload["disposition"] = disposition
    handler._json_response(HTTPStatus.CONFLICT, payload)


def _parse_provider_id_or_4xx(handler: WarRoomRequestHandler, raw: str) -> str | None:
    try:
        return parse_provider_id(raw)
    except ProviderConfigError:
        handler._json_error(HTTPStatus.BAD_REQUEST, "unknown provider id")
        return None


def _handle_post_token(
    handler: WarRoomRequestHandler, provider_raw: str, body: dict[str, Any]
) -> bool:
    provider_id = _parse_provider_id_or_4xx(handler, provider_raw)
    if provider_id is None:
        return True
    token = body.get("token")
    if not isinstance(token, str) or not token.strip():
        handler._json_error(HTTPStatus.BAD_REQUEST, "token must be non-blank")
        return True
    try:
        write_user_store_token(provider_id, token)
    except ValueError as exc:
        handler._json_error(HTTPStatus.BAD_REQUEST, str(exc))
        return True
    handler._json_response(HTTPStatus.OK, {"ok": True, "id": provider_id})
    return True


def _handle_post_forget(handler: WarRoomRequestHandler, provider_raw: str) -> bool:
    provider_id = _parse_provider_id_or_4xx(handler, provider_raw)
    if provider_id is None:
        return True
    forget_user_store_token(provider_id)
    handler._json_response(HTTPStatus.OK, {"ok": True, "id": provider_id})
    return True


def provider_api_path_exists(path: str) -> bool:
    """True when ``path`` is a registered provider API route."""

    if path == "/api/providers":
        return True
    if path.startswith(_RECOVERY_PREFIX):
        parts = path.removeprefix(_RECOVERY_PREFIX).strip("/").split("/")
        return (
            len(parts) == 2
            and bool(parts[0])
            and parts[1] in {"change", "retry", _CONTINUE_ACTION}
        )
    if not path.startswith("/api/providers/"):
        return False
    rest = path.removeprefix("/api/providers/").strip("/")
    if rest.endswith(_TOKEN_SUFFIX):
        provider_raw = rest[: -len(_TOKEN_SUFFIX)].strip("/")
    elif rest.endswith(_FORGET_SUFFIX):
        provider_raw = rest[: -len(_FORGET_SUFFIX)].strip("/")
    else:
        return False
    if not provider_raw or "/" in provider_raw:
        return False
    try:
        parse_provider_id(provider_raw)
    except ProviderConfigError:
        return False
    return True
