---
id: task_047
title: SWE worktree turn
tier: task
status: completed
parent: feat_009
children: []
depends_on:
  - task_045
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# SWE worktree turn

## Parent Feature

[feat_009](../../features/3_completed/feat_009_cursor_agent_backend.md) — Cursor agent backend.

## Depends on

- task_045 — SDK adapter (`run_role`)

## Acceptance criteria

- SWE `RoleTurn.cwd` is the active task worktree from `cascade/task/worktree.py` (`TaskRun.worktree` via `get_task_run(task_id)` / `create_task_worktree` boot path). MCP tools expose existing task registry tools (`register_task_tool`: `swe_read`, `swe_write`, `read_doc`, `swe_run_tests`, `swe_commit`, `fail_task`, etc.).
- After `run_role` completes successfully (`status == "finished"`), if the worktree diff touches paths under `docs/epics/` or `docs/features/`, **fail the turn closed** and **do not commit**. Reuse denylist logic from `cascade/task/git_tools.py` (`_assert_commit_paths_allowed` / `task_tool_guard` in `cascade/task/guard.py`).
- Allowed diffs commit only through `swe_commit` in `cascade/task/git_tools.py` on branch `task/{task_id}`. **Never push.** **Never commit on `main`.**
- **Failure classification** on a live Task (integrate with `cascade/task/wiring.py` / `cascade/task/failure.py`):
  - Retryable **startup** failure (`CursorAgentError` with `retryable` / `is_retryable` true): treat as **infra** flake under existing two-retry policy (`classify_error`, `maybe_retry`, `_route_failure` in `cascade/task/wiring.py`).
  - Run executed and failed (`RoleResult.status == "error"`): **spec**, fail closed (`fail_task`), no retry.
  - Non-retryable startup failure: **spec**, fail closed, no retry.
- Helper (e.g. `cascade/agent/swe_turn.py`) orchestrates: resolve worktree → build task MCP tools → `run_role` → post-run diff check → optional `swe_commit` when caller supplies message and diff is allowed.
- **Tests** (mock SDK / `run_role`): happy path commits on `task/{id}`; diff touching `docs/features/...` or `docs/epics/...` fails closed with no commit; retryable startup classified as infra vs run-error as spec.

## Files likely touched

- `cascade/agent/swe_turn.py` (or similar)
- `cascade/task/wiring.py` (hook startup vs run errors into `_route_failure` when SWE turn runs)
- `tests/agent/test_swe_turn.py`
- `tests/task/test_wiring.py` (if classification hooks need coverage)

## Implementation notes

Do not replace `_task_swe_node` quote behavior here — task_048 wires the graph. This task owns cwd, MCP tool list for SWE, post-run path gate, and commit/failure routing. `on_tests_finished` / `swe_run_tests` flow may remain separate; document how agent turn commits relate to test completion if both exist.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/agent/test_swe_turn.py tests/task/test_git_tools.py -q`

## Out of scope

- Planning scratch dirs (task_046).
- Epic/feature/boss `_quote` replacement (task_048).
- Model catalog / defaults (feat_010).
