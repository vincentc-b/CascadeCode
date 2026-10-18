---
id: task_065
title: Integration worktrees at dispatch
tier: task
status: completed
parent: feat_014
children: []
depends_on:
  - task_064
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-14
updated: 2026-10-14
---

# Integration worktrees at dispatch

## Parent Feature

[feat_014](../../features/3_completed/feat_014_workspace_contract.md) — Workspace contract and agent kickoff.

## Depends on

- task_064 — `cascade up`, product trunk resolution, supervisor process

## Acceptance criteria

- **Shared integration worktree module** (e.g. `cascade/workspace/integration_worktree.py`):
  - Paths: `.cascade/worktrees/{epic|feat|task}_{id}` (migrate from `cascade/task/worktree.worktree_path` which today uses `.cascade/worktrees/{task_id}` only).
  - **`create_integration_worktree(kind, work_id, *, branch, base_ref, root)`** using `git worktree add` from the **trunk** git dir (`cascade/task/worktree._env` pattern); record `IntegrationWorktree` (`kind`, `work_id`, `branch`, `path`, `base_sha`).
  - **`ensure_integration_worktree(...)`** / **`repair_missing_worktree`**: if branch exists and directory missing, recreate at the same path from branch (no new dispatch event).
  - Registry persisted under `.cascade/worktrees.json` or derived from `git worktree list` + board state (pick one; document idempotency).
- **`activate_epic`** (`cascade/watchdog/dispatch.py` + new epic activation helper):
  - Refuse unless human brief is on product trunk (feat_014: brief commit on trunk before cut — align with existing board/git checks or add explicit trunk HEAD vs epic doc check).
  - Cut `epic/{id}` from trunk when needed; add epic worktree; move epic doc in **epic worktree** board (trunk copy becomes pointer per spec — minimal pointer frontmatter or stub commit on trunk if full pointer is task_067+).
  - Does not checkout epic branch in operator `--root`.
- **`dispatch_feature`**: cut `feat/{id}` from current `epic/{parent}` tip; add `.cascade/worktrees/feat_{id}`; feature doc transitions happen in feature worktree board tree.
- **`dispatch_task`**: cut `task/{id}` from `feat/{parent}` tip; replace or wrap `create_task_worktree` so task SWE cwd is `.cascade/worktrees/task_{id}`; update `cascade/task/wiring.py` boot path.
- **`up` resume scan** (extend `cascade/workspace/up.py` or `cascade/watchdog/loop.py` startup hook):
  - Walk trunk `docs/epics` and each integration worktree's `docs/*/2_active/*.md`.
  - Legally active docs re-attach boot hooks only (no new queue dispatch events); missing worktree for live branch → `repair_missing_worktree`.
  - Unauthorized `2_active` files keep today's watchdog revert + toast (`cascade/watchdog/loop.py`).
- **Tests**:
  - `tests/workspace/test_integration_worktrees.py`: activate creates epic branch + worktree; dispatch feature/task create stacked branches and paths; delete worktree dir then repair restores without new `FeatureReadyToPlan` / `TaskDispatched`.
  - Update `tests/task/test_worktree.py` for new path convention `task_{id}`.
  - Extend `tests/watchdog/test_dispatch.py` if dispatch now requires initial commits / parent branches (use `tests.support.make_repo` patterns from merge tests).

## Files likely touched

- `cascade/workspace/integration_worktree.py`
- `cascade/watchdog/dispatch.py`
- `cascade/epic/mint.py` / `cascade/epic/boot.py` (activation side effects)
- `cascade/feature/boot.py`, `cascade/feature/registry.py` (cwd roots)
- `cascade/task/worktree.py`, `cascade/task/wiring.py`, `cascade/task/io_tools.py`
- `cascade/workspace/up.py`
- `cascade/board/store.py` (read/write doc relative to worktree root when needed)
- `tests/workspace/test_integration_worktrees.py`
- `tests/task/test_worktree.py`

## Implementation notes

- **Registry**: `.cascade/worktrees.json` with idempotent upsert per `(kind, work_id)`; `repair_missing_worktree` re-adds from existing branch only.
- **Brief on trunk**: `epic_brief_committed_on_trunk` uses `path_for_work_id(trunk, "HEAD", epic_id)` (same as git ls-tree at trunk HEAD). Refusal reason: `brief_not_on_trunk`.
- **Trunk pointer**: after activation, trunk `docs/epics/2_active/{id}_*.md` carries optional frontmatter `integration_branch` + `integration_worktree` (repo-relative path); body is a stub pointing editors at the epic worktree. Live spec is only on `epic/{id}` in `.cascade/worktrees/epic_{id}`.
- **Supervisor board (interim)**: `merged_board(trunk)` and `read_doc`/`move_doc` resolve the owning checkout via `_best_meta_for_id` (prefers `2_active`, feature worktree for task specs, de-prioritizes trunk pointers and task-worktree spec copies). Full War Room resolution remains task_067.
- **Epic worktree scrub**: child feature/task markdown copied by branch checkout is removed from the epic worktree at activation.
- **Resume**: `resume_legally_active_graphs` calls `repair_all_registered` only (graph re-attach is task_066).
- **`cascade.toml`**: still read from trunk only; hooks receive trunk `root` for config.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/workspace/test_integration_worktrees.py tests/task/test_worktree.py tests/watchdog/test_dispatch.py -q`

## Out of scope

- War Room attach/plan path resolution (task_067)
- Centralized `kickoff_turn` (task_066)
- Flight overlap report (task_068)
- Merge into `feat/{id}` (task_069)
