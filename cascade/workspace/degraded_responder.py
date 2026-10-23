"""Stdlib-only HTTP responder while the launcher holds the listen socket (feat_018_003)."""

from __future__ import annotations

import html
import json
import socket
from http import HTTPStatus
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cascade.workspace.supervisor_status import SupervisorStatus

_MAX_REQUEST_BYTES = 65536
_READ_CHUNK = 4096


def _read_request(conn: socket.socket) -> tuple[str, str] | None:
    buf = b""
    while b"\r\n\r\n" not in buf and len(buf) < _MAX_REQUEST_BYTES:
        try:
            chunk = conn.recv(_READ_CHUNK)
        except OSError:
            return None
        if not chunk:
            break
        buf += chunk
    if not buf:
        return None
    head = buf.split(b"\r\n\r\n", 1)[0]
    first = head.split(b"\r\n", 1)[0]
    parts = first.decode("iso-8859-1", errors="replace").split()
    if len(parts) < 2:
        return None
    method, path = parts[0], parts[1]
    return method, path


def _write_response(
    conn: socket.socket,
    *,
    status: HTTPStatus,
    content_type: str,
    body: bytes,
) -> None:
    header = (
        f"HTTP/1.1 {status.value} {status.phrase}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Cache-Control: no-store\r\n"
        f"Connection: close\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"\r\n"
    ).encode("ascii")
    try:
        conn.sendall(header + body)
    except OSError:
        pass


def _json_body(status: SupervisorStatus | None, *, error: str | None = None) -> bytes:
    payload: dict[str, object]
    if status is None:
        payload = {"error": error or "degraded", "state": "degraded"}
    else:
        payload = dict(status)
        if error is not None:
            payload["error"] = error
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _html_body(status: SupervisorStatus | None) -> bytes:
    last = (status or {}).get("last_error") or {}
    exit_code = last.get("exit_code")
    stderr_tail = last.get("stderr_tail") or ""
    next_action = (status or {}).get("next_action") or "Fix the worker and save source."
    message = last.get("message") or "Cascade worker is unavailable."
    parts = [
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">",
        "<title>Cascade unavailable</title></head><body>",
        "<h1>Service unavailable (503)</h1>",
        f"<p>{html.escape(str(message))}</p>",
    ]
    if exit_code is not None:
        parts.append(f"<p>Last exit code: {html.escape(str(exit_code))}</p>")
    if stderr_tail:
        parts.append(
            "<h2>Recent worker stderr</h2>"
            f"<pre>{html.escape(stderr_tail)}</pre>"
        )
    parts.append(f"<p><strong>Next:</strong> {html.escape(str(next_action))}</p>")
    parts.append("</body></html>")
    return "".join(parts).encode("utf-8")


def serve_one_degraded_request(
    conn: socket.socket,
    *,
    status: SupervisorStatus | None,
) -> None:
    """Answer a single HTTP request on ``conn`` with 503 diagnostics."""

    parsed = _read_request(conn)
    if parsed is None:
        return
    _method, path = parsed
    path_only = path.split("?", 1)[0]
    if path_only == "/api/health":
        body = _json_body(status)
        _write_response(
            conn,
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="application/json; charset=utf-8",
            body=body,
        )
        return
    if path_only.startswith("/api/"):
        body = _json_body(status, error="degraded")
        _write_response(
            conn,
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="application/json; charset=utf-8",
            body=body,
        )
        return
    body = _html_body(status)
    _write_response(
        conn,
        status=HTTPStatus.SERVICE_UNAVAILABLE,
        content_type="text/html; charset=utf-8",
        body=body,
    )
