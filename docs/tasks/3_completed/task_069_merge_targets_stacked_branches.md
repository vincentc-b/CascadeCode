---
id: task_069
title: Stacked branch merge targets
tier: task
status: completed
parent: feat_014
children: []
depends_on:
  - task_065
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-14
updated: 2026-10-14
---

# Stacked branch merge targets

## Parent Feature

[feat_014](../../features/3_completed/feat_014_workspace_contract.md) — Workspace contract and agent kickoff.

## Depends on

- task_065 — `task/{id}`, `feat/{id}`, `epic/{id}` branches and worktrees

## Acceptance criteria

- **Task merge** — refactor `cascade/boss/merge.merge_task_branch`:
  - Merge `task/{task_id}` into **`feat/{feature_id}`** (parent feature branch), not product trunk.
  - Merge/checkout occurs in **feature integration worktree** (or equivalent git context) while operator `--root` stays on trunk.
  - Preserve post-merge behavior: `move_doc` task to completed, `TaskMerged` event, teardown task worktree (`invoke_teardown`), `on_task_merged` rollup hook.
  - War Room `POST /api/merge_task_branch` continues to delegate here; update success/error reasons for wrong merge target.
- **Feature merge** — new **`merge_feature_branch(feature_id, *, root)`**:
  - When feature rollup gates pass (or explicit human action if separate from `try_complete_feature`), merge **`feat/{id}` → `epic/{epic_id}`** once; feature completion still moves doc to `3_completed` on feature worktree board.
  - Wire from `cascade/boss/rollup.py` / `try_complete_feature` at the point feat_014 describes “self-contained feature” landing on epic branch.
- **Epic promote** — extend human **`confirm_epic_complete`** path (`cascade/boss/epic_complete.py`) or companion **`promote_epic_to_trunk(epic_id)`**:
  - On human confirm when epic ready to close, merge **`epic/{id}` → product trunk** (not merely move markdown without branch merge when branch exists).
  - Refuse ambiguous trunk; use `resolve_product_trunk` from task_064.
- **`_mainline_branch` helpers**: exclude `epic/*`, `feat/*`, `task/*` consistently (update `cascade/boss/merge.py` and any task worktree root pickers).
- **Tests**:
  - `tests/boss/test_merge.py` — update expectations from trunk merge to feature merge; conflict/rollback cases preserved.
  - **`tests/boss/test_merge_targets.py`** (new): feature → epic and epic → trunk promotion with stacked repos (`tests.support` + worktrees from task_065 patterns).
  - `depends_on` / parallel task cap still apply on feature branch merges (document: task merges serialize into feature branch; cap unchanged).

## Files likely touched

- `cascade/boss/merge.py`
- `cascade/boss/rollup.py`
- `cascade/boss/epic_complete.py`
- `cascade/war_room/server.py` (`_handle_merge_task_branch`)
- `cascade/task/report.py` / `mark_awaiting_merge` (wording/target branch)
- `cascade/workspace/trunk.py`
- `tests/boss/test_merge.py`
- `tests/boss/test_merge_targets.py`

## Implementation notes

- **Human-only epic promote** aligns with existing `confirm_epic_complete(..., by="human")`; Boss still cannot merge code.
- **Risk (merge location vs board paths)**: completing a task updates task md on feature worktree; ensure `move_doc` uses correct board root after task_065.
- **Risk (feature complete without merge)**: if rollup gates pass before merge API called, define order: merge feat→epic required before or as part of `try_complete_feature` — match feat_014 “merged back as one unit” and record choice in test names.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/boss/test_merge.py tests/boss/test_merge_targets.py -q`

## Out of scope

- Auto-merge, rebase automation, stopping dispatch on overlap
- Remote push
- DESIGN.md (task_070)
