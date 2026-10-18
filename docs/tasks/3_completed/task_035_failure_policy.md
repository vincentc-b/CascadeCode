---
id: task_035
title: Task failure policy and fail_task
tier: task
status: completed
parent: feat_007
children: []
depends_on:
  - task_030
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Task failure policy and fail_task

## Parent Feature

[feat_007](../../features/3_completed/feat_007_task_execution.md) — Task execution and local branches.

## Depends on

- task_030 — `fail_closed_boot`, queue dest, graph lifecycle

## Acceptance criteria

- `failure.py`:
  - `classify_error(exc_or_result) -> Literal["infra", "spec"]` — infra/tool flake vs spec/test miss; **uncertain → `"spec"`** (fail closed).
  - `maybe_retry(task_id, kind, attempt, *, root) -> bool` — for `"infra"`, allow at most **2** retries (attempts 0–1 retry, attempt 2+ fail); for `"spec"`, never retry.
  - `fail_task(task_id: str, reason: str, *, root: Path) -> None`:
    - Append `TaskFailed { task_id, reason }` to the **parent Feature** queue (`append_event(feature_id, …)`).
    - Append War Room `Toast` with `payload.kind="task_failed"`, `id=task_id`, human-readable `message`/`body` including reason (mirror amendment toast pattern in `cascade/feature/amendments.py`).
    - Set Task doc `status=blocked` via board store; file **stays** in `docs/tasks/2_active/` (no column move).
    - Invoke task graph teardown: add `invoke_teardown(tier, work_id)` to `cascade/watchdog/hooks.py` if missing (mirror `invoke_boot`), then `invoke_teardown("task", task_id)`.
    - **Must not** call `dispatch_task` or change parallelism counting (watchdog already excludes `blocked`).
  - Wire `fail_closed_boot(task_id, reason)` from `cascade.task.boot` to call `fail_task` for `stale_parent_rev` and any boot-time fail-closed paths task_030 delegates here.
- Register `fail_task` on `register_task_tool` for SWE/graph use.
- `tests/task/test_failure.py` covers infra retry budget, immediate spec fail, uncertain → spec, queue + Toast payloads, blocked status without `2_active` move, teardown hook invoked, no dispatch side effects, and `stale_parent_rev` via `fail_closed_boot`.

## Files likely touched

- `cascade/task/failure.py`
- `cascade/watchdog/hooks.py` — `invoke_teardown` only
- `tests/task/test_failure.py`

## Implementation notes

Reuse `cascade.board.store.read_doc` / `save_doc` for status flip. Feature id from Task `parent`. Toast dest is `"war_room"`. Teardown should run registered hooks from task_031 worktree cleanup. Do not reimplement watchdog parallelism cap.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/task/test_failure.py -q`

## Out of scope

- SWE tool implementations (`task_033`, `task_034`), success path `awaiting_merge` (`task_036`), end-to-end wiring (`task_037`)
- Boss retry proposals (feat_008)
