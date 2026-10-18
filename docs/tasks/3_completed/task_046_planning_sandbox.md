---
id: task_046
title: Planning sandbox (epic, feature, boss)
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

# Planning sandbox (epic, feature, boss)

## Parent Feature

[feat_009](../../features/3_completed/feat_009_cursor_agent_backend.md) — Cursor agent backend.

## Depends on

- task_045 — SDK adapter (`run_role`)

## Acceptance criteria

- For **epic**, **feature**, and **boss** role turns, build a fresh scratch directory as `RoleTurn.cwd` containing **only** the documents that role may read (per existing path sandbox / read rules). After `run_role` returns, remove the scratch directory; writes the SDK agent made inside scratch **do not** appear in the repo. Repo mutations happen **only** when a Cascade MCP tool runs.
- MCP server definitions for the turn wrap **existing guarded Cascade tools** for that tier — do not reimplement guards in the adapter:
  - Epic: tools registered via `register_epic_tool` / `epic_tools()` (e.g. `mint_feature`, `write_doc`, `read_doc`, `record_decision`, comment tools from `cascade/epic/` wiring).
  - Feature: `register_feature_tool` / `feature_tools()` (e.g. `mint_task`, `write_doc`, `read_doc`, `list_children`, comment and amendment tools from `cascade/feature/wiring.py`).
  - Boss: wrappers over existing boss dispatch surfaces (e.g. `dispatch_feature`, `dispatch_task` from watchdog dispatch — **not** new `dispatch_*` or `activate_epic` in the agent backend). May integrate with `list_board` / `compute_boss_view` read paths where appropriate; order execution stays in `cascade/boss/orders.py` / queue consumer.
- Wrappers invoke the same Python functions the graphs already use (`invoke_tool` patterns in `cascade/epic/graph.py`, `cascade/feature/graph.py`, or direct registry calls with existing guard checks).
- `RoleResult.tool_effects` lists **only** effects Cascade applied through its own tools during the turn (not scratch filesystem noise).
- Public helper(s) (e.g. `cascade/agent/planning_turn.py`) that: materialize scratch + allowed docs → assemble MCP list → call `run_role` → teardown scratch → return `RoleResult`.
- **Tests** (temp repo + temp scratch): fake or mocked `run_role` / SDK. Assert (1) a file written only under scratch never appears in the git worktree, (2) scratch dir is gone after the turn, (3) invoking an MCP tool reaches the underlying guarded function (mock/spy on e.g. `mint_feature` or `write_doc`).

## Files likely touched

- `cascade/agent/planning_sandbox.py` (or similar)
- `cascade/agent/mcp_wrappers.py` (or similar)
- `tests/agent/test_planning_sandbox.py`

## Implementation notes

Boss graph (`cascade/boss/graph.py`) remains a queue consumer; this task only prepares boss **model** turns (scratch + tools), not a second dispatch primitive. Epic/feature graph `invoke_tool` is the reference for how guarded tools are invoked today.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/agent/test_planning_sandbox.py -q`

## Out of scope

- SWE task worktree turns and git commit path (task_047).
- Replacing `_quote` nodes in epic/feature graphs (task_048).
- Model defaults and resolver (feat_010).
