---
id: task_030
title: Task graph runtime and boot hook
tier: task
status: completed
parent: feat_007
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Task graph runtime and boot hook

## Parent Feature

[feat_007](../../features/3_completed/feat_007_task_execution.md) — Task execution and local branches.

## Depends on

_(none — feat_002 boot hooks and feat_005 feature queue patterns are complete.)_

## Acceptance criteria

- New package `cascade/task/` with:
  - `TaskGraphState` in `state.py`: `task_id`, `feature_id`, reducer-backed `messages`, `last_queue_offset`, and `skill_playbooks: list[dict]` (default empty; populated by task_032).
  - SQLite checkpointer at `{repo_root}/.cascade/checkpoints/{task_id}.sqlite`; LangGraph thread id equals the task work id; validate tier via `parse_work_id`.
  - `registry.py`: `register_task_tool`, `task_tools`, `clear_task_tools` (mirror feature registry).
  - `graph.py`: `ensure_task_graph`, `ingest_queue`, `invoke_tool`; deterministic single SWE node (no external LLM), no stack router; `ingest_queue` drains `read_events(task_id, offset)` into role=`event` messages without an SWE turn.
- `boot.py`:
  - `install_task_boot_hook(root)` registers `register_boot_hook("task", boot_task)` idempotently and stores repo root (mirror `install_feature_boot_hook`).
  - `boot_task(task_id)`:
    - No-op for non-task tier or missing task doc (mirror `boot_feature`).
    - Read own Task doc and parent Feature doc **at the Task’s pinned `parent_rev` only** (use board/git helpers; do not read Epic, siblings, comments, or War Room).
    - If Task `parent_rev` is non-null and differs from the parent Feature file’s current `last_commit_touching` SHA on the main repo: call `fail_closed_boot(task_id, reason="stale_parent_rev")` and return without emitting `TaskActivated` or compiling a graph.
    - Otherwise: `ensure_task_graph`, append `TaskActivated { task_id, feature_id }` to the **parent Feature graph queue** (`append_event(feature_id, …)`), then `ingest_queue`.
  - `fail_closed_boot(task_id: str, reason: str) -> None`: public boot-local path that records failure intent for later wiring (minimal: set internal/boot state or emit only what task_035 completes); **must not** call `dispatch_task`. Task_035 will call this for all terminal failures including `stale_parent_rev`.
- No worktree creation, no SWE repo tools, no skill loading in this task.
- `tests/task/test_runtime.py` covers checkpoint persistence, queue ingest idempotency, `TaskActivated` dest=payload feature_id, stale `parent_rev` → `fail_closed_boot` (no activation event), boot hook registration, and isolated task graph state.

## Files likely touched

- `cascade/task/__init__.py`
- `cascade/task/state.py`
- `cascade/task/checkpoint.py`
- `cascade/task/graph.py`
- `cascade/task/registry.py`
- `cascade/task/boot.py`
- `tests/task/test_runtime.py`

## Implementation notes

Mirror `cascade/feature/{state,checkpoint,graph,registry,boot}.py`. Queue dest for `TaskActivated` is the parent Feature id from Task frontmatter `parent`. Reuse `cascade.board.store.read_doc`, `last_commit_touching`, `cascade.watchdog.events.append_event`, and `cascade.watchdog.hooks.register_boot_hook`. Do not pin or rewrite Task `parent_rev` at boot (Task keeps the SHA minted/dispatch wrote).

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/task/test_runtime.py -q`

## Out of scope

- Worktree/branch (`task_031`), skills context (`task_032`), path sandbox and SWE I/O (`task_033`), git tools (`task_034`), full `fail_task` / teardown / blocked status (`task_035`), merge report toasts (`task_036`), end-to-end wiring (`task_037`)
- `WarRoomHTTPServer` / watchdog loop hook install (task_037)
- `TaskMerged`, merge-to-mainline (feat_008)
