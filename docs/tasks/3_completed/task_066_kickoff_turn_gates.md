---
id: task_066
title: Kickoff turn authorization gates
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

# Kickoff turn authorization gates

## Parent Feature

[feat_014](../../features/3_completed/feat_014_workspace_contract.md) — Workspace contract and agent kickoff.

## Depends on

- task_064 — supervisor `up` entry and watchdog loop

## Acceptance criteria

- **`kickoff_turn(reason: KickoffReason) -> None`** (e.g. `cascade/workspace/kickoff.py` + `KickoffReason` in `cascade/workspace/types.py`):
  - Sole path that invokes **`run_role`** / **`run_planning_role_turn`** / SWE **`run_swe_turn`** for roster agents (refactor call sites from `cascade/epic/graph.py`, `cascade/feature/graph.py`, `cascade/task/graph.py`, `cascade/agent/planning_turn.py`, human chat wiring in `cascade/epic/wiring.py`, `cascade/feature/wiring.py`, `cascade/boss/model_turn.py` as needed).
  - Allowed `kind` values match feat_014 table: `activate`, `dispatch`, `human_message`, `comment`, `queue_event`, `resume_inflight` (blocked task re-dispatch maps to `dispatch`).
  - Model resolution failure toasts via existing `toast_model_config_failure` and **does not** call the model (fail closed).
- **Opening turn after activate/dispatch**:
  - Successful `activate_epic` / `dispatch_feature` triggers one planning opening turn (existing boot → `ingest_queue` path) but opening turn tools must **not** call `dispatch_feature` / `dispatch_task` (guard in MCP wrappers / planning sandbox already partially exists — verify and test).
  - `dispatch_task` triggers SWE implementation turn (not a no-op boot).
- **`up` resume** (`resume_inflight`):
  - Re-attach graphs from checkpointer; if a turn was interrupted, continue; if idle, stay idle — **no** new `FeatureReadyToPlan` / `TaskDispatched` event.
  - Does not kick opening turn again for already-idle active epics/features.
- **Non-kickoff paths must not call the model** (regression tests with monkeypatched `run_role` / `run_planning_role_turn`):
  - `mint_feature` / `mint_task` tools (epic/feature graphs) — file stays in backlog.
  - Doc left in backlog with `ready_to_plan` and no dispatch.
  - `watchdog_tick` with no new authorized edge (including flight refresh once task_068 lands — stub/mock flight hook here).
  - War Room **`POST /api/attach`**, **`GET /api/doc/*`**, **`/plan/*` page** — no model call.
  - Boss noticing ready work without order (`cascade/boss/view.py`, drain consumer idle).
- **Tests** (`tests/workspace/test_kickoff.py`, extend `tests/agent/test_adapter.py` only if shared helper moves):
  - Table-driven: each forbidden action → assert mock not called.
  - Authorized: `activate_epic` / `dispatch_feature` / `dispatch_task` / human chat on attached epic → exactly one model invocation path.
  - Resume: simulate checkpoint mid-turn vs idle epic across `up` hook.

## Files likely touched

- `cascade/workspace/kickoff.py`
- `cascade/workspace/types.py` (`KickoffReason`)
- `cascade/watchdog/dispatch.py` (call `kickoff_turn` after boot)
- `cascade/workspace/up.py` (resume scan integration)
- `cascade/epic/graph.py`, `cascade/feature/graph.py`, `cascade/task/graph.py`
- `cascade/epic/wiring.py`, `cascade/feature/wiring.py`, `cascade/boss/model_turn.py`
- `cascade/agent/mcp_wrappers.py` (dispatch tool guard)
- `tests/workspace/test_kickoff.py`

## Implementation notes

- Boot (`cascade/epic/boot.py`, `feature/boot.py`, `task/boot.py`) attaches graphs and resolves models — distinguish **boot** vs **model turn** in docs and tests per feat_014.
- **`CURSOR_API_KEY`**: remain env-only; `kickoff_turn` relies on `cascade/agent/adapter.run_role` (no workspace fallback).
- **Risk (opening turn scope)**: feat_014 risk #1 — opening turn may mint children; tests should document current behavior; do not add timer-based wakeups.
- **Risk (parallel with task_065)**: kickoff may land before worktrees exist — coordinate so opening turn `cwd` is integration worktree when task_065 is merged; until then, tests may skip cwd assertion.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/workspace/test_kickoff.py -q`

## Out of scope

- Worktree creation (task_065)
- War Room read paths (task_067)
- Flight report (task_068)
- DESIGN.md edits (task_070)
