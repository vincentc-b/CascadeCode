"""Stable hash of loaded Cascade Python source (stdlib-only)."""

from __future__ import annotations

import hashlib
from pathlib import Path

_DEFAULT_SOURCE_ROOT = Path(__file__).resolve().parents[1]


def source_fingerprint(root: Path = _DEFAULT_SOURCE_ROOT) -> str:
    """Return a stable fingerprint of the Python source loaded by the supervisor."""

    digest = hashlib.sha256()
    try:
        paths = sorted(
            root.rglob("*.py"), key=lambda path: path.relative_to(root).as_posix()
        )
        for path in paths:
            relative = path.relative_to(root).as_posix().encode()
            digest.update(len(relative).to_bytes(4, "big"))
            digest.update(relative)
            body = path.read_bytes()
            digest.update(len(body).to_bytes(8, "big"))
            digest.update(body)
    except OSError as exc:
        # A checkout can briefly remove or replace files.  Treat that as a
        # source change rather than letting a read race preserve stale code.
        return f"unreadable:{type(exc).__name__}:{exc}"
    return digest.hexdigest()
