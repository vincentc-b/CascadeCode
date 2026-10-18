"""War Room HTTP routes for pending epic amendments (task_029)."""

from __future__ import annotations

import re
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from cascade.amendments.store import AmendmentNotFound, list_pending_for_epic, read_amendment
from cascade.epic.amendments import ResolveAmendmentError, resolve_amendment
from cascade.epic.guard import EpicToolDenied
from cascade.war_room.serialize import amendment_summary_to_dict
from cascade.war_room.views import default_epic_graph_id

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler

_AMD_ID_RE = re.compile(r"^amd_\d+$")
_DIFF_SUFFIX = "/diff"
_RESOLVE_SUFFIX = "/resolve"


def register_amendment_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/amendments", handle_get_amendments_list)


def try_handle_amendment_get(handler: WarRoomRequestHandler) -> bool:
    path = handler.path.split("?", 1)[0]
    if not path.startswith("/api/amendments/"):
        return False
    rest = path.removeprefix("/api/amendments/").strip("/")
    if not rest.endswith(_DIFF_SUFFIX):
        handler._json_error(HTTPStatus.NOT_FOUND, "not found")
        return True
    amd_id = rest.removesuffix(_DIFF_SUFFIX).strip("/")
    if not amd_id or "/" in amd_id:
        handler._json_error(HTTPStatus.NOT_FOUND, "not found")
        return True
    if not _AMD_ID_RE.match(amd_id):
        handler._json_error(HTTPStatus.NOT_FOUND, "not found")
        return True
    handle_get_amendment_diff(handler, amd_id)
    return True


def try_handle_amendment_post(handler: WarRoomRequestHandler, body: dict[str, Any]) -> bool:
    path = handler.path.split("?", 1)[0]
    prefix = "/api/amendments/"
    if not path.startswith(prefix) or not path.endswith(_RESOLVE_SUFFIX):
        return False
    middle = path[len(prefix) : -len(_RESOLVE_SUFFIX)].strip("/")
    if not middle or "/" in middle:
        handler._json_error(HTTPStatus.NOT_FOUND, "not found")
        return True
    if not _AMD_ID_RE.match(middle):
        handler._json_error(HTTPStatus.NOT_FOUND, "not found")
        return True
    handle_post_amendment_resolve(handler, middle, body)
    return True


def handle_get_amendments_list(handler: WarRoomRequestHandler) -> None:
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query, keep_blank_values=True)
    epic_id = (params.get("epic_id") or [""])[0].strip()
    if not epic_id:
        handler._json_error(HTTPStatus.BAD_REQUEST, "missing epic_id")
        return
    pending = list_pending_for_epic(epic_id, root=handler.server.root)
    payload = [amendment_summary_to_dict(row) for row in pending]
    handler._json_response(HTTPStatus.OK, payload)


def handle_get_amendment_diff(handler: WarRoomRequestHandler, amd_id: str) -> None:
    try:
        record = read_amendment(amd_id, root=handler.server.root)
    except AmendmentNotFound:
        handler._json_error(HTTPStatus.NOT_FOUND, f"not found: {amd_id}")
        return
    repo = handler.server.root
    diff_path = record.diff_path
    if not diff_path.is_absolute():
        diff_path = repo / diff_path
    if not diff_path.is_file():
        handler._json_error(HTTPStatus.NOT_FOUND, f"not found: {amd_id}")
        return
    body = diff_path.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def handle_post_amendment_resolve(
    handler: WarRoomRequestHandler,
    amd_id: str,
    body: dict[str, Any],
) -> None:
    decision = body.get("decision")
    if not isinstance(decision, str) or not decision.strip():
        handler._json_error(HTTPStatus.BAD_REQUEST, "missing decision")
        return
    note = body.get("note")
    if note is not None and not isinstance(note, str):
        handler._json_error(HTTPStatus.BAD_REQUEST, "invalid note")
        return
    revised_text = body.get("revised_text")
    if revised_text is not None and not isinstance(revised_text, str):
        handler._json_error(HTTPStatus.BAD_REQUEST, "invalid revised_text")
        return

    try:
        record = read_amendment(amd_id, root=handler.server.root)
    except AmendmentNotFound:
        handler._json_error(HTTPStatus.NOT_FOUND, f"not found: {amd_id}")
        return

    default_epic = default_epic_graph_id(root=handler.server.root)
    requested_raw = body.get("epic_id")
    if isinstance(requested_raw, str) and requested_raw.strip():
        requested_epic = requested_raw.strip()
    else:
        requested_epic = default_epic

    if record.epic_id != requested_epic:
        handler._json_error(
            HTTPStatus.FORBIDDEN,
            f"amendment {amd_id} belongs to {record.epic_id}, not {requested_epic}",
        )
        return

    try:
        epic_rev = resolve_amendment(
            amd_id,
            decision.strip(),
            note=note,
            revised_text=revised_text,
            epic_id=record.epic_id,
            root=handler.server.root,
        )
    except AmendmentNotFound:
        handler._json_error(HTTPStatus.NOT_FOUND, f"not found: {amd_id}")
        return
    except EpicToolDenied as exc:
        handler._json_error(HTTPStatus.FORBIDDEN, str(exc))
        return
    except ResolveAmendmentError as exc:
        handler._json_error(HTTPStatus.BAD_REQUEST, str(exc))
        return

    handler._json_response(HTTPStatus.OK, {"epic_rev": epic_rev})


def amendment_get_path_exists(path: str, *, root: Path) -> bool:
    """True when ``path`` is a registered amendment GET sub-route."""

    if not path.startswith("/api/amendments/"):
        return False
    rest = path.removeprefix("/api/amendments/").strip("/")
    if not rest.endswith(_DIFF_SUFFIX):
        return False
    amd_id = rest.removesuffix(_DIFF_SUFFIX)
    return bool(_AMD_ID_RE.match(amd_id))
