"""Comment sidecar record types (feat_005 / DESIGN.md §10.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

CommentState = Literal["open", "resolved"]
CommentAuthor = Literal[
    "human",
    "feature_lead",
    "feature_architect",
    "epic_manager",
    "epic_architect",
]

AGENT_AUTHORS = frozenset(
    {"feature_lead", "feature_architect", "epic_manager", "epic_architect"}
)


@dataclass(frozen=True)
class Comment:
    id: str
    doc_id: str
    section: str
    anchor: str | None
    author: str
    body: str
    parent: str | None
    state: CommentState
    blocking: bool
    created: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "section": self.section,
            "anchor": self.anchor,
            "author": self.author,
            "body": self.body,
            "parent": self.parent,
            "state": self.state,
            "blocking": self.blocking,
            "created": self.created.astimezone().isoformat().replace("+00:00", "Z"),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Comment:
        anchor = raw.get("anchor")
        parent = raw.get("parent")
        created_raw = raw.get("created")
        if not isinstance(created_raw, str):
            raise ValueError("comment.created must be a string")
        created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        if created.tzinfo is None or created.utcoffset() is None:
            raise ValueError("comment.created must be timezone-aware")
        state = raw.get("state")
        if state not in ("open", "resolved"):
            raise ValueError("comment.state must be open or resolved")
        return cls(
            id=str(raw["id"]),
            doc_id=str(raw["doc_id"]),
            section=str(raw["section"]),
            anchor=anchor if anchor is None or isinstance(anchor, str) else None,
            author=str(raw["author"]),
            body=str(raw["body"]),
            parent=parent if parent is None or isinstance(parent, str) else None,
            state=state,
            blocking=bool(raw.get("blocking", False)),
            created=created,
        )
