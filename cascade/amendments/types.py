"""Amendment sidecar record types (feat_006)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

AmendmentState = Literal["pending", "accepted", "rejected", "revise_pending"]


@dataclass(frozen=True)
class Amendment:
    id: str
    feature_id: str
    epic_id: str
    section: str
    diff_path: Path
    proposed_text: str
    rationale: str
    state: AmendmentState
    created: datetime
    revised_text: str | None = None
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "feature_id": self.feature_id,
            "epic_id": self.epic_id,
            "section": self.section,
            "diff_path": self.diff_path.as_posix(),
            "proposed_text": self.proposed_text,
            "rationale": self.rationale,
            "state": self.state,
            "created": self.created.astimezone().isoformat().replace("+00:00", "Z"),
        }
        if self.revised_text is not None:
            payload["revised_text"] = self.revised_text
        if self.reject_reason is not None:
            payload["reject_reason"] = self.reject_reason
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Amendment:
        created_raw = raw.get("created")
        if not isinstance(created_raw, str):
            raise ValueError("amendment.created must be a string")
        created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        if created.tzinfo is None or created.utcoffset() is None:
            raise ValueError("amendment.created must be timezone-aware")

        state = raw.get("state")
        if state not in ("pending", "accepted", "rejected", "revise_pending"):
            raise ValueError("amendment.state is invalid")

        diff_raw = raw.get("diff_path")
        if not isinstance(diff_raw, str) or not diff_raw.strip():
            raise ValueError("amendment.diff_path must be a non-empty string")

        revised = raw.get("revised_text")
        reject_reason = raw.get("reject_reason")

        return cls(
            id=str(raw["id"]),
            feature_id=str(raw["feature_id"]),
            epic_id=str(raw["epic_id"]),
            section=str(raw["section"]),
            diff_path=Path(diff_raw),
            proposed_text=str(raw["proposed_text"]),
            rationale=str(raw["rationale"]),
            state=state,
            created=created,
            revised_text=revised if revised is None or isinstance(revised, str) else None,
            reject_reason=(
                reject_reason
                if reject_reason is None or isinstance(reject_reason, str)
                else None
            ),
        )
