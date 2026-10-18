"""Append-only human chat sidecars per persisting graph id."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.workspace.doc_root import read_doc_resolved, resolve_doc_worktree
from cascade.workspace.integration_worktree import locate_trunk
from cascade.watchdog.lock import process_lock

_CHAT_DIR = Path("docs") / "_war_room" / "chat"


def graph_id_is_valid(graph_id: str) -> bool:
    if not graph_id or "/" in graph_id or "\\" in graph_id or graph_id in {".", ".."}:
        return False
    return True


def _sidecar_path(root: Path, graph_id: str) -> Path:
    if not graph_id_is_valid(graph_id):
        raise ValueError(f"invalid graph_id: {graph_id!r}")
    return root / _CHAT_DIR / f"{graph_id}.jsonl"


def read_messages(graph_id: str, *, root: Path) -> list[dict]:
    """Return all messages for ``graph_id`` (empty if sidecar missing)."""

    repo = _chat_repo(graph_id, root=root)
    path = _sidecar_path(repo, graph_id)
    with process_lock:
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def append_transcript_message(
    graph_id: str,
    *,
    author: str,
    body: str,
    root: Path,
) -> dict:
    """Append one transcript line (human or role) to the chat sidecar."""

    repo = _chat_repo(graph_id, root=root)
    if _is_task_tier(graph_id, root=root):
        raise TaskTierChatError(graph_id)
    text = body.strip()
    if not text:
        raise ValueError("empty body")
    message = {
        "id": uuid.uuid4().hex,
        "graph_id": graph_id,
        "author": author,
        "body": text,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    path = _sidecar_path(repo, graph_id)
    line = (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    with process_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(line)
    return message


def append_message(graph_id: str, body: str, *, root: Path) -> dict:
    """Append one human message; return the stored message dict."""

    if _is_task_tier(graph_id, root=root):
        raise TaskTierChatError(graph_id)
    text = body.strip()
    if not text:
        raise ValueError("empty body")
    return append_transcript_message(graph_id, author="human", body=text, root=root)


def remove_message(graph_id: str, message_id: str, *, root: Path) -> None:
    """Drop one message from the sidecar by id (e.g. rollback after failed graph ingest)."""

    repo = _chat_repo(graph_id, root=root)
    path = _sidecar_path(repo, graph_id)
    with process_lock:
        if not path.is_file():
            return
        kept: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                kept.append(stripped)
                continue
            if isinstance(row, dict) and row.get("id") == message_id:
                continue
            kept.append(stripped)
        if kept:
            path.write_text(
                "\n".join(kept) + "\n",
                encoding="utf-8",
            )
        else:
            path.unlink(missing_ok=True)


class TaskTierChatError(Exception):
    def __init__(self, graph_id: str) -> None:
        self.graph_id = graph_id
        super().__init__(graph_id)


def _chat_repo(graph_id: str, *, root: Path) -> Path:
    trunk = locate_trunk(resolve_root(root))
    try:
        return resolve_doc_worktree(graph_id, root=trunk)
    except NotFound:
        return trunk


def _is_task_tier(graph_id: str, *, root: Path) -> bool:
    trunk = locate_trunk(resolve_root(root))
    try:
        doc = read_doc_resolved(graph_id, root=trunk)
    except NotFound:
        return False
    return doc.meta.tier == "task"
