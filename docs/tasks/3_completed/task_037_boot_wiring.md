---
id: task_037
title: Task boot wiring and tool load
tier: task
status: completed
parent: feat_007
children: []
depends_on:
  - task_030
  - task_031
  - task_032
  - task_033
  - task_034
  - task_035
  - task_036
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Task boot wiring and tool load

## Parent Feature

[feat_007](../../features/3_completed/feat_007_task_execution.md) — Task execution and local branches.

## Depends on

- task_030 — runtime, `boot_task`, `install_task_boot_hook`
- task_031 — worktree create/teardown registration
- task_032 — skill playbooks
- task_033 — `swe_read` / `swe_write` / `read_doc`
- task_034 — `swe_run_tests` / `swe_commit`
- task_035 — `fail_task` / `fail_closed_boot` integration
- task_036 — awaiting-merge report

## Acceptance criteria

- `wiring.py`:
  - `load_task_tools()` registers all task SWE tools (`swe_read`, `swe_write`, `read_doc`, `swe_run_tests`, `swe_commit`, `fail_task`) idempotently.
  - `boot_task_wired(task_id: str) -> None` registered via `register_boot_hook("task", boot_task_wired)` from `load_task_wiring(root)` (second hook after task_030 `boot_task`; runs only when dispatch succeeded and stale-rev check passed in the first hook): create worktree → load skills into graph state → set `TaskRun.state` to `coding` (or run one deterministic SWE turn); on success path after green tests, call `mark_awaiting_merge`; route tool errors through `classify_error` / `maybe_retry` / `fail_task`.
  - **One** general SWE LangGraph node (no stack router; graph compile remains task_030).
- `load_task_wiring(root)` / `install_task_wiring(root)` idempotently registers the wired boot hook and calls `load_task_tools()`; invoked next to `install_task_boot_hook` in server/loop (task_030 hook must register first).
- Minimal edits: `cascade/war_room/server.py` calls `install_task_boot_hook(self.root)` and `install_task_wiring(self.root)` immediately after the feature installs (mirror epic/feature).
- Same pattern in `cascade/watchdog/loop.py` at watchdog startup (mirror task_018).
- `tests/task/test_wiring.py` integration-style test with temp repo: simulated `TaskDispatched` → `invoke_boot("task", id)` creates worktree, tools registered, `TaskActivated` on feature queue, no push, teardown on `fail_task`.

## Files likely touched

- `cascade/task/wiring.py`
- `cascade/war_room/server.py` — install hook line only
- `cascade/watchdog/loop.py` — install hook line only
- `tests/task/test_wiring.py`

## Implementation notes

Follow `cascade/feature/wiring.py` + task_018 server/loop installs. Do not import wiring from `cascade/__init__.py`. Watchdog already calls `invoke_boot("task", work_id)` after successful `dispatch_task`. Keep orchestration in wiring; do not duplicate guard or git logic from sibling modules.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/task/test_wiring.py -q`

## Out of scope

- Changing dispatch law (`cascade/watchdog/dispatch.py`)
- UI merge button / `TaskMerged` (feat_008)
- External LLM integration
