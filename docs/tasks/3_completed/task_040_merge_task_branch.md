---
id: task_040
title: Human merge_task_branch
tier: task
status: completed
parent: feat_008
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Human merge_task_branch

## Parent Feature

[feat_008](../../features/3_completed/feat_008_boss_and_rollup.md) — Boss agent and completion rollup.

## Depends on

_(none — wave A)_

## Acceptance criteria

- `cascade/boss/merge.py` implements `merge_task_branch(task_id: str, *, root: Path | None = None) -> MergeResult` (typed result with `ok`, `reason`, `merge_sha`, `branch`) callable **only from the human path** (no Boss tool registration in this task).
- Success path:
  - Resolve repo root; load task via board store; require tier `task` and status appropriate for merge (e.g. `active` or `awaiting_merge` in `2_active`—match feat_007 `mark_awaiting_merge` states used in the codebase).
  - Verify local git branch `task/{task_id}` exists on the mainline repo (reuse patterns from `cascade/task/worktree.py` / `git_tools.py` where helpful).
  - Merge that branch into the current mainline checkout (local only, no push); on success obtain `merge_sha`.
  - `move_doc(task_id, "completed", ...)` so the file lands in `3_completed`.
  - Append queue event **`TaskMerged`** with payload `{ task_id, branch: "task/{id}", merge_sha }` to the parent feature graph dest and a **`Toast`** (or existing war_room notification pattern) with kind `task_merged` on dest `war_room`.
- Failure path (no board move): branch missing, not a git repo, merge conflict, dirty merge abort, task not found, wrong tier/column — return structured failure without partial `move_doc`.
- `tests/boss/test_merge.py` uses a temp git repo + minimal board layout: happy merge moves task to `3_completed` and writes `TaskMerged`; missing branch returns error; conflict scenario returns error and leaves task in `2_active`.

## Files likely touched

- `cascade/boss/merge.py`
- `tests/boss/test_merge.py`

## Implementation notes

This is the **library** implementation behind DESIGN §11 Human `merge_task_branch`. Do **not** change `cascade/war_room/server.py` `_handle_merge_task_branch` stub (task_044 swaps route to call this). Teardown task worktree if feat_007 registers runs—call existing teardown hooks if merge implies graph end. Boss must never invoke this module.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/boss/test_merge.py -q`

## Out of scope

- HTTP handler / UI merge button wiring
- Feature rollup (`try_complete_feature`) — task_041 / task_044
- Auto-merge
- Boss dispatch tools
- Editing `tests/war_room/test_dispatch_routes.py`
