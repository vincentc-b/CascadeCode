---
id: task_004
title: Event schema and append-only JSONL queues
tier: task
status: completed
parent: feat_002
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-09
---

# Event schema and append-only JSONL queues

## Parent Feature

[feat_002](../../features/3_completed/feat_002_watchdog_queue_dispatch.md) — Watchdog, event queue, and dispatch law.

Honor the locked types and queue API in that Feature and DESIGN.md §8.

## Depends on

None (feat_001 board store is a Feature dependency, not a Task edge).

## Acceptance criteria

- Package `cascade.watchdog` exposes `Principal`, `Event`, `DispatchRequest`, `DispatchResult`, `append_event`, and `read_events` from `cascade/watchdog/__init__.py`.
- `Principal = Literal["human", "boss"]`.
- `Event`: `type: str`, `ts: datetime` (timezone-aware), `payload: object` (JSON object on disk), `dest: str` (graph queue id).
- `DispatchRequest`: `kind: epic | feature | task`, `id: WorkId`, `by: Principal`.
- `DispatchResult`: `ok: bool`, `reason: str | null` where reason is one of `unauthorized`, `unmet_deps`, `cap`, `not_found`, `bad_state`; `event: Event | null`.
- Queue files live at `docs/_queue/{dest}.jsonl` under the repo root; one `Event` per line; append-only (no rewrite of prior lines).
- Valid dest ids (filename stem before `.jsonl`): `epic_{id}`, `feat_{id}`, `task_{id}`, `war_room`, `boss` (and any work id string used as a graph queue key).
- `append_event(dest, event) -> None` appends one JSON line; rejects unsafe `dest` values (path segments, empty).
- `read_events(dest, after_offset) -> ([Event], new_offset)` returns events after a byte offset and the offset after consumed lines; malformed lines are skipped without stalling progress; partial trailing line waits for the next read.
- Event type names and payload fields used by feat_002 dispatch and UI toasts (DESIGN.md §8 plus feat_002 locks):
  - `EpicActivated` — `{ epic_id, by }` (by = human on success).
  - `FeatureReadyToPlan` — `{ id, by }` (by = human | boss). May also include `feature_id` mirroring `id` for DESIGN.md §8 compatibility.
  - `TaskDispatched` — `{ id, feature_id, by, skills }` (skills = effective in-repo paths as strings; by = human | boss).
  - `Toast` — illegal board move notification; type name `Toast` (existing code). Dest `war_room`. Payload at minimum: `kind` (e.g. `illegal_move`), `id` (work id), `message`, `reason` (e.g. `unauthorized`).
- Unit tests in `tests/watchdog/test_queue.py` cover round-trip append/read with offsets, append-only bytes, timezone-aware timestamps, and malformed-line skipping.

## Files likely touched

- `cascade/watchdog/types.py`
- `cascade/watchdog/events.py`
- `cascade/watchdog/__init__.py`
- `tests/watchdog/test_queue.py`

## Implementation notes

Serialize `ts` as ISO-8601 UTC in JSON. Keep queue I/O independent of dispatch law. Share `process_lock` with board git commits if concurrent append is possible. Do not implement dispatch, hooks, config, or the watchdog loop in this Task.

## Skills

_(none)_

## Test plan

`pytest tests/watchdog/test_queue.py`

## Out of scope

- `activate_epic`, `dispatch_feature`, `dispatch_task`
- Watchdog poll loop and illegal-move revert logic
- Boot/teardown hooks
- `cascade.toml` / `task_parallelism`
- Skill path validation at dispatch time
