"""Map ``war_room`` queue events to feat_003 Toast JSON."""

from __future__ import annotations

import re

from cascade.watchdog.types import Event

_AMENDMENT_DIFF_RE = re.compile(r"Review diff at ([^\s]+)\.")

_API_KINDS = frozenset(
    {
        "amendment",
        "comment",
        "blocked",
        "task_failed",
        "task_merge_blocked",
        "task_merged",
        "task_ready",
        "illegal_dispatch",
        "epic_ready_to_close",
        "orphan",
        "task_retry_proposed",
        "flight_overlap",
        "brief_imported",
        "epic_plan_approved",
        "feature_review_opened",
    }
)

# Event type ``Toast`` (cascade/watchdog/loop.py ``_toast``):
#   payload.kind ``illegal_move`` -> API kind ``illegal_dispatch``
#   payload.message -> body; payload.id -> link ``/api/doc/{id}``
#
# Future Toast payload kinds that already match _API_KINDS pass through unchanged.
# Non-Toast event types are skipped.


def events_to_toasts(events: list[Event]) -> list[dict]:
    out: list[dict] = []
    for event in events:
        mapped = _event_to_toast(event)
        if mapped is not None:
            out.append(mapped)
    return out


def _event_to_toast(event: Event) -> dict | None:
    if event.type != "Toast":
        return None
    payload = event.payload
    raw_kind = payload.get("kind")
    if not isinstance(raw_kind, str):
        return None
    if raw_kind == "illegal_move":
        kind = "illegal_dispatch"
    elif raw_kind in _API_KINDS:
        kind = raw_kind
    else:
        kind = "illegal_dispatch"
    body = payload.get("message") or payload.get("body")
    if not isinstance(body, str) or not body.strip():
        work_id = payload.get("id")
        body = f"{kind}: {work_id}" if isinstance(work_id, str) else kind
    link: str | None = None
    work_id = payload.get("id")
    if isinstance(work_id, str) and work_id.strip():
        link = f"/api/doc/{work_id.strip()}"
    url = payload.get("url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        link = url
    toast: dict = {"kind": kind, "body": body, "link": link}
    if kind == "amendment":
        if isinstance(work_id, str) and work_id.strip():
            toast["epic_id"] = work_id.strip()
        match = _AMENDMENT_DIFF_RE.search(body)
        if match:
            toast["diff_path"] = match.group(1)
    if kind == "epic_ready_to_close":
        epic_id = payload.get("epic_id")
        if isinstance(epic_id, str) and epic_id.strip():
            toast["epic_id"] = epic_id.strip()
        elif isinstance(work_id, str) and work_id.strip():
            toast["epic_id"] = work_id.strip()
    if kind == "orphan" and isinstance(work_id, str) and work_id.strip():
        toast["orphan_id"] = work_id.strip()
    if kind == "task_retry_proposed" and isinstance(work_id, str) and work_id.strip():
        toast["task_id"] = work_id.strip()
    if kind == "flight_overlap":
        epic_id = payload.get("epic_id")
        if isinstance(epic_id, str) and epic_id.strip():
            toast["epic_id"] = epic_id.strip()
        overlap_ids = payload.get("work_ids")
        if isinstance(overlap_ids, list):
            toast["work_ids"] = [str(item) for item in overlap_ids]
        overlap_paths = payload.get("paths")
        if isinstance(overlap_paths, list):
            toast["paths"] = [str(item) for item in overlap_paths]
    return toast
