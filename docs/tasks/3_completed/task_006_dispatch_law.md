---
id: task_006
title: activate_epic, dispatch_feature, and dispatch_task
tier: task
status: completed
parent: feat_002
children: []
depends_on:
  - task_004
  - task_005
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-09
---

# activate_epic, dispatch_feature, and dispatch_task

## Parent Feature

[feat_002](../../features/3_completed/feat_002_watchdog_queue_dispatch.md) — Watchdog, event queue, and dispatch law.

`move_doc` from feat_001 is **only** called from this module (and completion paths in feat_008) for lifecycle transitions into `2_active`. Planning-graph tools must not import `move_doc` for children.

## Depends on

- [task_004](../../tasks/3_completed/task_004_event_queue.md) (Event, queue append)
- [task_005](../../tasks/3_completed/task_005_config_skills_hooks.md) (`task_parallelism`, hooks, skill paths)

## Acceptance criteria

- `cascade/watchdog/__init__.py` exports `activate_epic`, `dispatch_feature`, and `dispatch_task`.
- All three return `DispatchResult` with reason codes: `unauthorized`, `unmet_deps`, `cap`, `not_found`, `bad_state` (no event on failure unless spec says otherwise).

**`activate_epic(id, by)`**

- Refuse unless `by == human` → `unauthorized`.
- Refuse unless the Epic exists → `not_found`.
- Refuse unless `status in {backlog, ready_to_plan}` → `bad_state`.
- Refuse unless every `depends_on` id is completed (`3_completed`) → `unmet_deps`.
- On success: set `ready_to_plan` as appropriate, then `move_doc(id, active)`; file lands in `docs/epics/2_active/` with status consistent with feat_001 active column rules.
- Append `EpicActivated` to queue dest `epic_{id}` (work id) with payload `{ epic_id, by }`.
- Invoke `boot_hook("epic", id)` after a successful move and event.
- Boss cannot activate → tested.

**`dispatch_feature(id, by)`**

- Refuse unless `by in {human, boss}` → `unauthorized`.
- Refuse unless Feature exists → `not_found`.
- Refuse unless `status in {backlog, ready_to_plan}` → `bad_state`.
- Refuse unless all `depends_on` are completed → `unmet_deps`.
- On success: set `ready_to_plan`, `move_doc(id, active)`, emit `FeatureReadyToPlan` with `{ id, by }` on the feature’s queue dest, invoke `boot_hook("feature", id)`.

**`dispatch_task(id, by, skills=None)`**

- Refuse unless `by in {human, boss}` → `unauthorized`.
- Refuse unless Task exists with valid parent Feature → `not_found` / `bad_state` as appropriate.
- Refuse unless all `depends_on` are completed → `unmet_deps`.
- Refuse when count of Tasks in `docs/tasks/2_active/` with `status=active` is `>= task_parallelism(root)` → `cap`. **`status=blocked` in `2_active` does not consume a slot.**
- Over cap: do **not** move the file; emit nothing (optional future `TaskDispatchQueued` is not required); caller retries later.
- If `skills is not None`: override the Task’s effective skill list on the same write as activation; every path must exist in-repo or refuse → `bad_state`.
- On success: `move_doc(id, active)` (or equivalent single write placing the Task in `2_active` with `status=active`), emit `TaskDispatched` `{ id, feature_id, by, skills }` on dest `task_{id}`, invoke `boot_hook("task", id)`.
- Re-dispatch of a `blocked` Task already in `2_active` is a legal success path (new Human/Boss order); do **not** treat `TaskFailed` as implicit dispatch (feat_007 owns failure teardown).
- Tests in `tests/watchdog/test_dispatch.py` cover principals, dependencies, cap (including blocked not counting), skills override/rejection, boot hooks, and unauthorized principals.

## Files likely touched

- `cascade/watchdog/dispatch.py`
- `cascade/watchdog/__init__.py`
- `tests/watchdog/test_dispatch.py`

## Implementation notes

Use `list_board` / `read_doc` / `move_doc` / `write_doc` from `cascade.board`. Emit events via `append_event` from task_004. Run boot hooks outside the board lock if needed to avoid deadlock with `watchdog_tick` in tests. Cap check before skill validation so over-cap is not masked by a bad skill path.

## Skills

_(none)_

## Test plan

`pytest tests/watchdog/test_dispatch.py`

## Out of scope

- Filesystem watchdog loop (`watchdog_tick`, illegal-move revert)
- Boss sequencing policy (feat_008)
- Task failure, `TaskFailed`, teardown hooks on failure (feat_007)
- LangGraph graph boot implementations (feat_004/005/007)
