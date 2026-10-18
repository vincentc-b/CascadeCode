"""Epic LangGraph state schema."""

from __future__ import annotations

import operator
from typing import Annotated, NotRequired, TypedDict


class EpicGraphState(TypedDict):
    epic_id: str
    messages: Annotated[list[dict], operator.add]
    last_queue_offset: int
    model_id: NotRequired[str]
    model_ids: NotRequired[dict[str, str]]
    model_sources: NotRequired[dict[str, str]]
    provider_ids: NotRequired[dict[str, str]]
    provider_sources: NotRequired[dict[str, str]]
