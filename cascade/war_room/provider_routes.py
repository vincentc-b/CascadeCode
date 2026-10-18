"""War Room HTTP routes for provider status and credential store (task_075)."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from cascade.agent.credentials import forget_user_store_token, write_user_store_token
from cascade.agent.errors import ProviderConfigError
from cascade.agent.providers import parse_provider_id, probe_providers
from cascade.watchdog.config import read_providers_config
from cascade.war_room.serialize import providers_view_to_dict

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler

_TOKEN_SUFFIX = "/token"
_FORGET_SUFFIX = "/forget"


def register_provider_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/providers", handle_get_providers)


def handle_get_providers(handler: WarRoomRequestHandler) -> None:
    config = read_providers_config(handler.server.root)
    statuses = probe_providers()
    payload = providers_view_to_dict(config.default, statuses)
    handler._json_response(HTTPStatus.OK, payload)


def try_handle_provider_post(handler: WarRoomRequestHandler, body: dict[str, Any]) -> bool:
    path = handler.path.split("?", 1)[0]
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
