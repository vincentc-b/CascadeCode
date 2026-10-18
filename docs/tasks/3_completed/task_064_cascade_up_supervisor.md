---
id: task_064
title: cascade up supervisor entry
tier: task
status: completed
parent: feat_014
children: []
depends_on:
  - task_063
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-14
updated: 2026-10-14
---

# cascade up supervisor entry

## Parent Feature

[feat_014](../../features/3_completed/feat_014_workspace_contract.md) — Workspace contract and agent kickoff.

## Depends on

- task_063 — `init_workspace`, board scaffold, `cascade.toml` template

## Acceptance criteria

- **`up(root, host="127.0.0.1", port=8765)`** (e.g. `cascade/workspace/up.py`):
  - Requires git repo with board layout (`docs/epics` etc.); if missing, error directing operator to `cascade init`.
  - **`resolve_product_trunk(root) -> str`**: `main` when `refs/heads/main` exists; else the unique local branch that is not `epic/*`, `feat/*`, or `task/*` and is an ancestor of every other such branch (reuse/extend `_mainline_branch` logic in `cascade/boss/merge.py` with prefix filters). If zero or multiple candidates, refuse `up` with a clear error (same refusal contract as `activate_epic` will use in task_065).
  - Refuses when `git rev-parse --abbrev-ref HEAD` at `--root` is not the product trunk (does **not** checkout `epic/*`, `feat/*`, or `task/*` in `--root`).
  - Starts **one** supervisor: War Room HTTP (`cascade.war_room.server.serve` + `serve_forever` in a thread) and watchdog loop (`cascade.watchdog.loop.run_watchdog` in a thread or shared loop) bound to the same `root`.
  - **One lock per root**: second concurrent `cascade up` on the same root refuses (file lock under `.cascade/supervisor.lock` or equivalent; in-process `threading.RLock` alone is insufficient). Document lock release on exit.
  - **`up` is not dispatch**: no `move_doc`, no new `EpicActivated` / `FeatureReadyToPlan` / `TaskDispatched` events.
  - Binds host via existing `assert_loopback_host` (127.0.0.1 only unless tests override).
- **CLI**: `cascade up [--root PATH] [--host 127.0.0.1] [--port 8765]` wired in `cascade/cli.py`.
- **Resume stub (minimal for this task)**: call site hook documented for task_065/066 — `up` may install boot hooks then idle; full legal-active scan and worktree repair belong in task_065/066. This task must not invoke `activate_epic` / `dispatch_*` from `up`.
- **Tests** (`tests/workspace/test_up.py`):
  - Initialized repo on trunk: `up` starts server (use short-lived thread + HTTP GET `/api/board` or health).
  - Repo checked out on `task/foo` branch: `up` refuses.
  - Two `up` attempts on same root: second refuses while first holds lock.
  - Missing board dirs: refuses with init hint.

## Files likely touched

- `cascade/workspace/up.py`
- `cascade/workspace/trunk.py` (`resolve_product_trunk`)
- `cascade/cli.py`
- `cascade/war_room/server.py` (only if a shared shutdown hook is needed)
- `cascade/watchdog/loop.py` (optional: inject `stop_when` for tests)
- `cascade/boss/merge.py` (factor shared trunk helper if moved)
- `tests/workspace/test_up.py`

## Implementation notes

- Today `python -m cascade.war_room` runs HTTP only; feat_014 contract makes **`cascade up`** the operator entry. Leave module `__main__` as read-only dev shortcut if desired; document in module docstring.
- **`cascade.toml` is read from trunk checkout** at `root`; child worktrees are out of scope here.
- **Risk (resume depth)**: task_064 vs task_065 boundary — this task wires processes; task_065 adds worktree scan/repair; task_066 adds graph re-attach without re-dispatch. Avoid duplicating resume logic in both places.
- **Risk (in-flight turn continue)**: interrupt mid-turn resume is task_066; `up` here must not call the model.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/workspace/test_up.py -q`

## Out of scope

- Integration worktree creation (task_065)
- `kickoff_turn` / opening model turns (task_066)
- `resolve_doc_worktree`, flight report, merge retargeting
- Checking out integration branches in `--root`
