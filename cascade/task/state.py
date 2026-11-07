"""Task LangGraph state schema."""

from __future__ import annotations

import operator
from typing import Annotated, NotRequired, TypedDict


class TaskGraphState(TypedDict):
    task_id: str
    feature_id: str
    messages: Annotated[list[dict], operator.add]
    last_queue_offset: int
    skill_playbooks: list[dict]
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
