---
id: task_048
title: Graph wiring (role turns)
tier: task
status: completed
parent: feat_009
children: []
depends_on:
  - task_045
  - task_046
  - task_047
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Graph wiring (role turns)

## Parent Feature

[feat_009](../../features/3_completed/feat_009_cursor_agent_backend.md) — Cursor agent backend.

## Depends on

- task_045 — SDK adapter
- task_046 — planning sandbox turns
- task_047 — SWE worktree turn

## Acceptance criteria

- **Epic graph** (`cascade/epic/graph.py`): `_manager_node` and `_architect_node` stop emitting deterministic `_quote` paraphrases as the role message. Build a `RoleTurn` from graph state plus a **caller-supplied** `model_id`, run planning sandbox + `run_role`, append result `text` as that role's message. If `model_id` is missing/blank, **do not** call `run_role` — fail that turn (surface error in messages). Do not read `cascade.toml`; do not invent defaults (feat_010).
- **Feature graph** (`cascade/feature/graph.py`): same for `_feature_lead_node` and `_feature_architect_node`.
- **Task graph** (`cascade/task/graph.py`): `_task_swe_node` uses SWE worktree turn helper (task_047) instead of `_quote`; honors task failure/retry policy via existing wiring.
- **Boss**: wire where a **boss model reply** is produced (not the queue consumer in `cascade/boss/graph.py` / `process_boss_event` in `cascade/boss/orders.py`, which stays order-driven). Use planning sandbox boss path + `run_role` for lieutenant/model turns (e.g. War Room ask-boss / future boss chat path). Backend must not gain new `dispatch_*`, `activate_epic`, or column-move primitives.
- **Errors**: planning and boss turns surface startup failures and run errors in room/graph messages; they **do not** apply task infra retry by themselves. Task SWE retries remain in `cascade/task/wiring.py` only for live tasks per task_047.
- **State**: never store Cursor agent id in LangGraph checkpoint state. Existing `register_*_tool` registries, guards, and queue handling remain Cascade-owned.
- **Tests**: update tests that assert `_quote` / "observed …" copy to inject `model_id` and a fake adapter or mocked `run_role`; cover missing `model_id` → no SDK call.

## Files likely touched

- `cascade/epic/graph.py`
- `cascade/feature/graph.py`
- `cascade/task/graph.py`
- `cascade/war_room/server.py` or boss chat integration point (if boss reply is surfaced there)
- `tests/epic/test_graph.py`
- `tests/feature/test_graph.py`
- `tests/task/test_graph.py`

## Implementation notes

Graph nodes may accept `model_id` via state field populated by a future feat_010 resolver; until then tests pass explicit ids. `invoke_tool` paths stay unchanged for human/tool-driven actions. Inject adapter at module boundary for testability (e.g. optional `run_role_fn` parameter or swappable module attribute).

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/epic/test_graph.py tests/feature/test_graph.py tests/task/test_graph.py -q`

## Out of scope

- Model catalog, `cascade.toml` defaults, board filtering (feat_010, feat_011).
- Cloud agents and remote checkpointers.
