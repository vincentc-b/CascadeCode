"""Server-side UI attachment state for War Room chat.

Default when none set: **no graph attached** (``null``). The server does not
auto-attach an epic in ``2_active``; clients must ``POST /api/attach`` before
``POST /api/chat/{graph_id}`` succeeds.
"""

from __future__ import annotations


class AttachmentState:
    """In-memory set of graph ids the human has attached."""

    __slots__ = ("_attached",)

    def __init__(self) -> None:
        self._attached: set[str] = set()

    def attach(self, graph_id: str) -> None:
        self._attached.add(graph_id)

    def detach(self, graph_id: str) -> None:
        self._attached.discard(graph_id)

    def is_attached(self, graph_id: str) -> bool:
        return graph_id in self._attached
