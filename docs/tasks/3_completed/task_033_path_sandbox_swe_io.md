---
id: task_033
title: Path sandbox and swe_read/swe_write
tier: task
status: completed
parent: feat_007
children: []
depends_on:
  - task_030
  - task_031
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Path sandbox and swe_read/swe_write

## Parent Feature

[feat_007](../../features/3_completed/feat_007_task_execution.md) — Task execution and local branches.

## Depends on

- task_030 — task tool registry and graph invoke path
- task_031 — `TaskRun.worktree` for repo-relative file operations

## Acceptance criteria

- `guard.py`: `task_tool_guard(path, op, *, task_id, worktree_root, board_root) -> bool` (or raise `TaskToolDenied`):
  - **Deny all writes** under `docs/epics/**` and `docs/features/**` (paths resolved under `worktree_root`).
  - Allow reads of other repo files inside the task worktree when not denied.
  - Skill playbook text must **not** bypass the denylist.
- `io_tools.py`:
  - `swe_read(path, *, task_id, task_run, root) -> str` — read file under worktree after guard check.
  - `swe_write(path, content, *, task_id, task_run, root) -> None` — write under worktree after guard check.
  - `read_doc(work_id, *, task_id, root) -> WorkDoc` — **only** own Task id and parent Feature id, each at the Task’s pinned `parent_rev` (git show / board pin read); deny Epic, sibling tasks/features, comment sidecars, War Room paths.
  - No amendment, comment, drop-in, or dispatch tools.
- Register `swe_read`, `swe_write`, and task-scoped `read_doc` on `register_task_tool` (registration function exported for wiring; full load order is task_037).
- `tests/task/test_guard.py` covers denylist writes, allowed code edits, `read_doc` scope, stale pin behavior on feature read, and skill text cannot override denylist.

## Files likely touched

- `cascade/task/guard.py`
- `cascade/task/io_tools.py`
- `tests/task/test_guard.py`

## Implementation notes

Mirror patterns from `cascade/feature/guard.py` and `cascade/feature/scoped_docs.py` but scoped to Task rules in DESIGN.md §5.3 and §11 Task Team. Resolve paths relative to `task_run.worktree`, not the board checkout. Reuse board store/git helpers for pinned parent Feature reads.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/task/test_guard.py -q`

## Out of scope

- `swe_run_tests` / `swe_commit` (`task_034`), failure policy (`task_035`), wiring (`task_037`)
- Writes to `/docs/tasks` plan files (Task does not amend its own board doc via SWE tools)
