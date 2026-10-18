---
id: task_068
title: Flight report and overlap toasts
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

# Flight report and overlap toasts

## Parent Feature

[feat_014](../../features/3_completed/feat_014_workspace_contract.md) — Workspace contract and agent kickoff.

## Depends on

- task_065 — in-flight branches, worktrees, and `base_sha` on cut

## Acceptance criteria

- **`flight_report(root) -> FlightReport`** (e.g. `cascade/workspace/flight.py`):
  - Lists in-flight features and tasks (and epics when active) with `IntegrationWorktree` metadata from task_065.
  - For each entry, `changed_paths[work_id]` = `git diff --name-only base_sha..branch_tip` (repo-relative); no LLM.
  - **`overlaps`**: path-set intersections between two in-flight features, and between a feature and commits on `epic/{id}` after the feature's `base_sha` (feat_014 flight section).
  - Deterministic ordering for stable tests.
- **`GET /api/flight`** on War Room (`cascade/war_room/server.py` + register route): JSON serialization of current `FlightReport`.
- **Watchdog refresh**: each `watchdog_tick` (or `up` loop) recomputes report; **does not** merge, rebase, block dispatch, or call the model.
- **Epic home UI**: War Room epic lens shows in-flight features, changed paths, and overlap hints (extend `war_room.js` / board API payload — minimal table or panel on epic focus).
- **Overlap toast**: when a **new** overlap appears vs previous tick, append `Toast` to `war_room` queue (`docs/_queue/war_room.jsonl`) with stable kind (e.g. `flight_overlap`); idempotent dedupe per overlap signature (pattern from `cascade/boss/epic_complete.py` surfaced prompts).
- **Tests** (`tests/workspace/test_flight.py`):
  - Two feature branches touching same file → overlap entry with that path.
  - Feature cut before epic commit lands → overlap with epic delta paths.
  - Tick refresh does not invoke `run_role` mock.
  - `GET /api/flight` returns JSON matching dataclass.

## Files likely touched

- `cascade/workspace/flight.py`
- `cascade/workspace/types.py` (`FlightReport`, overlap records)
- `cascade/watchdog/loop.py` (hook after `_tick`)
- `cascade/war_room/server.py`
- `cascade/war_room/serialize.py`
- `cascade/war_room/static/war_room.js`
- `tests/workspace/test_flight.py`

## Implementation notes

- Boss may **read** flight data via existing view hooks later; do not auto-dispatch on overlap (feat_008 order-driven).
- **Risk (feature vs epic overlap definition)**: precise git range for “commits on epic/{id} after feature cut” — use merge-base / `base_sha..epic/HEAD` and document in test fixtures; if spec ambiguous, prefer conservative path listing and note in test docstring.
- **Risk (in-flight detection)**: tie to `2_active` docs on feature/task worktrees plus branch existence, not merely branch presence without active doc.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/workspace/test_flight.py -q`

## Out of scope

- Auto-merge / blocking dispatch on overlap
- LLM conflict prediction
- DESIGN.md (task_070)
