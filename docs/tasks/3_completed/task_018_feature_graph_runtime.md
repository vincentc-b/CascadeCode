---
id: task_018
title: Feature graph runtime and local checkpointer
tier: task
status: completed
parent: feat_005
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Feature graph runtime and local checkpointer

## Parent Feature

[feat_005](../../features/3_completed/feat_005_feature_team.md) — Feature Team, comments, and drop-in.

## Depends on

_(none — feat_004 epic runtime and feat_002 boot hooks are complete.)_

## Acceptance criteria

- New package `cascade/feature/` with `FeatureGraphState` in `state.py`: `feature_id`, reducer-backed `messages`, `last_queue_offset`.
- Local SQLite checkpointer at `{repo_root}/.cascade/checkpoints/{feature_id}.sqlite`; LangGraph thread id equals the feature work id (e.g. `feat_005`).
- `ensure_feature_graph`, `ingest_human`, `ingest_queue`, and `invoke_tool` in `graph.py` mirror epic behavior: one human turn runs ingest → `feature_lead` → `feature_architect` (deterministic, no external LLM); `ingest_queue` drains `read_events(feature_id, offset)` into role=`event` messages without a lead/architect turn.
- Tool registry `register_feature_tool` / `feature_tools` / `clear_feature_tools` in `registry.py`; `invoke_tool` records success as role=`tool` messages.
- `boot_feature(work_id)` + `install_feature_boot_hook(root)` register `register_boot_hook("feature", boot_feature)` idempotently; on boot: read feature doc, call `pin_parent(feature_id, parent_id)` from `cascade.board.store` so frontmatter `parent_rev` is the parent epic file’s last commit SHA (committed via existing `write_doc`), then `ensure_feature_graph` and `ingest_queue`. If git has no commit for the parent yet, `parent_rev` may be null per board helpers.
- `install_feature_boot_hook(root)` is invoked from `WarRoomHTTPServer` and `cascade/watchdog/loop.py` (same explicit pattern as `install_epic_boot_hook`). No registration from `cascade/__init__.py` or import side effects in `cascade.watchdog`.
- `tests/feature/test_runtime.py` covers checkpoint persistence, one-turn roles, queue idempotency, boot hook + `parent_rev` pin, tools, and isolated feature state.

## Files likely touched

- `cascade/feature/__init__.py`
- `cascade/feature/state.py`
- `cascade/feature/checkpoint.py`
- `cascade/feature/graph.py`
- `cascade/feature/boot.py`
- `cascade/feature/registry.py`
- `cascade/watchdog/loop.py`
- `cascade/war_room/server.py`
- `tests/feature/test_runtime.py`
- `pyproject.toml` (only if LangGraph deps missing — they should already be present from feat_004)

## Implementation notes

Graph id is the feature work id, matching queue dest from `dispatch_feature`. Cache SQLite connections per checkpoint path like `cascade/epic/checkpoint.py`. Role nodes quote the latest human/event content deterministically. `boot_feature` must no-op for non-feature tiers or missing docs (mirror `boot_epic`). Do not register feature tools beyond the registry scaffold in this task.

## Skills

_(none)_

## Test plan

- `python3 -m pytest tests/feature/test_runtime.py -q`
- `python3 -m pytest tests/watchdog/test_hooks.py tests/watchdog/test_dispatch.py -q`

## Out of scope

- `tool_guard`, scoped `read_doc` / `write_doc`, `mint_task`, comments, briefing pack, `propose_epic_amendment` (tasks task_019–task_025)
- Epic graph changes except shared watchdog/server hook install lines
- Moving feat_005 or editing planning markdown beyond this task’s own doc if needed for tests
