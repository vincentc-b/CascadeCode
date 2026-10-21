"""Small stdio JSON-RPC transport shared by Cascade MCP servers."""

from __future__ import annotations

import json
import sys
from typing import Any, Literal

Framing = Literal["jsonl", "content-length"]


def read_message() -> tuple[dict[str, Any], Framing] | None:
    """Read modern MCP JSONL, retaining legacy Content-Length support."""

    first = sys.stdin.buffer.readline()
    if not first:
        return None
    decoded = first.decode("utf-8", errors="replace").strip()
    if decoded.startswith("{"):
        return json.loads(decoded), "jsonl"

    headers: dict[str, str] = {}
    line = decoded
    while True:
        if line:
            key, separator, value = line.partition(":")
            if not separator:
                return None
            headers[key.strip().lower()] = value.strip()
        next_line = sys.stdin.buffer.readline()
        if not next_line:
            return None
        line = next_line.decode("utf-8", errors="replace").strip()
        if not line:
            break
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8")), "content-length"


def write_message(payload: dict[str, Any], *, framing: Framing) -> None:
    encoded = json.dumps(payload).encode("utf-8")
    if framing == "jsonl":
        sys.stdout.buffer.write(encoded + b"\n")
    else:
        header = f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii")
        sys.stdout.buffer.write(header)
        sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()
