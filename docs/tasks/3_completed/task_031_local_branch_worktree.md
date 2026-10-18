---
id: task_031
title: Local branch and git worktree
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

# Local branch and git worktree

## Parent Feature

[feat_007](../../features/3_completed/feat_007_task_execution.md) — Task execution and local branches.

## Depends on

- task_030 — task boot hook and graph id conventions

## Acceptance criteria

- `TaskRun` dataclass (or typed record) in `worktree.py` with fields: `task_id`, `branch` (`task/{task_id}`), `worktree` (`Path`), `parent_rev`, `skills` (list of repo-relative paths), `state` in `{booting, coding, testing, awaiting_merge, failed, merged}`.
- `create_task_worktree(task_id: str, *, root: Path, parent_rev: str | None, skills: list[str]) -> TaskRun`:
  - Branch name exactly `task/{task_id}`.
  - Create branch from current mainline HEAD in the **board repo** (`root`), then add an isolated git worktree at a deterministic path under `{root}/.cascade/worktrees/{task_id}/` (or equivalent under `.cascade/`).
  - Initial `TaskRun.state` is `booting`.
  - **Never** `git push`. **Never** commit plan-dispatch or board column moves from this module.
- `remove_task_worktree(task_run: TaskRun, *, root: Path) -> None`: remove the worktree directory; **do not** delete the local branch (human merge is feat_008).
- `register_teardown_hook("task", …)` wrapper or helper that calls `remove_task_worktree` for the active run (registration only; invocation on failure is task_035).
- `tests/task/test_worktree.py` uses a temp git repo: branch exists, worktree is separate from main checkout, teardown removes worktree but branch remains, no push invoked.

## Files likely touched

- `cascade/task/worktree.py`
- `tests/task/test_worktree.py`

## Implementation notes

Use local `git` subprocess or existing `cascade.board.gitutil` helpers if present; do not add remote operations. Mainline HEAD is the repo at `root` (where `/docs` lives), not the worktree path. Reuse `cascade.watchdog.hooks.register_teardown_hook` for cleanup registration.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/task/test_worktree.py -q`

## Out of scope

- LangGraph runtime (`task_030`), skill text loading (`task_032`), SWE tools (`task_033`–`task_034`), failure toasts and `status=blocked` (`task_035`), diff summary (`task_036`), orchestration in `wiring.py` (`task_037`)
