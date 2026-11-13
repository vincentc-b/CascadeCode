"""Epic LangGraph state schema."""

from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from cascade.agent.message_history import append_recent_messages


class EpicGraphState(TypedDict):
    epic_id: str
    messages: Annotated[list[dict], append_recent_messages]
    last_queue_offset: int
    model_id: NotRequired[str]
    model_ids: NotRequired[dict[str, str]]
    model_sources: NotRequired[dict[str, str]]
    provider_ids: NotRequired[dict[str, str]]
    provider_sources: NotRequired[dict[str, str]]
    reasoning_ids: NotRequired[dict[str, str]]
    reasoning_sources: NotRequired[dict[str, str]]
    flex_modes: NotRequired[dict[str, bool | None]]
    flex_waiver_ids: NotRequired[dict[str, str]]
    flex_waiver_receipt_ids: NotRequired[dict[str, str]]
    flex_waiver_source_work_ids: NotRequired[dict[str, str]]
