---
id: task_034
title: swe_run_tests and swe_commit
tier: task
status: completed
parent: feat_007
children: []
depends_on:
  - task_031
  - task_033
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# swe_run_tests and swe_commit

## Parent Feature

[feat_007](../../features/3_completed/feat_007_task_execution.md) — Task execution and local branches.

## Depends on

- task_031 — worktree path and branch name
- task_033 — guard rules for paths touched by commits

## Acceptance criteria

- `git_tools.py`:
  - `swe_run_tests(*, task_id, task_run, root, cmd: list[str] | None = None) -> dict` — run pytest (default `python3 -m pytest -q`) with `cwd=task_run.worktree`; return exit code and captured output summary; does not push.
  - `swe_commit(message: str, *, task_id, task_run, root) -> str`:
    - Refuse unless current branch in the worktree is exactly `task/{task_id}`.
    - Refuse if staged/changed paths include any under `docs/epics/` or `docs/features/` (reuse guard denylist logic or call into `task_tool_guard`).
    - Create a normal git commit on the task branch only; return commit SHA.
    - **Never** push; **never** commit plan-dispatch or board lifecycle changes.
- Register both tools on `register_task_tool`.
- `tests/task/test_git_tools.py` covers happy commit on task branch, refused wrong branch, refused epic/feature path in commit, and test runner invoked in worktree.

## Files likely touched

- `cascade/task/git_tools.py`
- `tests/task/test_git_tools.py`

## Implementation notes

Run git with `-C worktree` (or subprocess cwd). Branch detection via `git rev-parse --abbrev-ref HEAD` inside worktree. For test runs, respect repo’s existing pytest layout; optional `cmd` override for tests only.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/task/test_git_tools.py -q`

## Out of scope

- Failure classification / retries (`task_035`), awaiting_merge reporting (`task_036`), full boot wiring (`task_037`)
- Auto-merge or `TaskMerged` (feat_008)
