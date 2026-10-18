---
id: task_036
title: Branch and diff summary for merge
tier: task
status: completed
parent: feat_007
children: []
depends_on:
  - task_031
  - task_034
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Branch and diff summary for merge

## Parent Feature

[feat_007](../../features/3_completed/feat_007_task_execution.md) — Task execution and local branches.

## Depends on

- task_031 — branch name and `TaskRun` state field
- task_034 — tests-pass signal from `swe_run_tests`

## Acceptance criteria

- `report.py`:
  - `summarize_diff(task_run: TaskRun, *, root: Path) -> str` — short summary vs mainline merge-base (e.g. `git diff --stat` or `--name-status` between mainline HEAD and `task/{task_id}`); not a full patch dump.
  - `mark_awaiting_merge(task_id: str, task_run: TaskRun, *, root: Path) -> None`:
    - Set `TaskRun.state=awaiting_merge`.
    - Emit War Room `Toast` (preferred for feat_003 UI) with body containing branch `task/{task_id}` and the diff summary; use a distinct `kind` that maps through `cascade/war_room/toasts.py` (extend mapper if needed, e.g. `task_ready` or reuse an existing allowed kind with clear body text).
    - **Do not** merge. **Do not** emit `TaskMerged` (feat_008).
- Callable from wiring after green tests (task_037); unit-test without full graph.
- `tests/task/test_report.py` covers summary length/shape, state transition, Toast append to `war_room` queue, and no `TaskMerged` event.

## Files likely touched

- `cascade/task/report.py`
- `cascade/war_room/toasts.py` — only if a new Toast kind needs API mapping
- `tests/task/test_report.py`

## Implementation notes

Compare branch in board repo (`root`) or worktree branch tracking the same commits. Reuse `append_event("war_room", Event(type="Toast", …))` pattern. Human merge and column move to `3_completed` remain feat_008.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/task/test_report.py -q`

## Out of scope

- `merge_task_branch`, `TaskMerged`, moving Task to `3_completed` (feat_008)
- Failure path (`task_035`)
