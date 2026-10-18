---
id: task_012
title: Epic graph runtime and local checkpointer
tier: task
status: completed
parent: feat_004
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-10
---

# Epic graph runtime and local checkpointer

## Parent Feature

[feat_004](../../features/3_completed/feat_004_epic_team.md) — Epic Team graph.

## Depends on

_(none listed — feat_002 hooks and queue are assumed available.)_

## Acceptance criteria

- `EpicGraphState` in `cascade/epic/state.py` with `epic_id`, reducer-backed `messages`, and `last_queue_offset`.
- Local SQLite checkpointer at `{repo_root}/.cascade/checkpoints/{epic_id}.sqlite`; thread id equals epic work id.
- `ensure_epic_graph`, `ingest_human`, `ingest_queue`, and `invoke_tool` in `cascade/epic/graph.py` with behavior specified in feat_004 task notes.
- One human turn runs ingest → manager → architect and appends exactly one `epic_manager` and one `epic_architect` message referencing the latest human or event input (no external LLM).
- `ingest_queue` drains `read_events(epic_id, offset)` into role=`event` messages and advances `last_queue_offset` without a manager/architect turn.
- Tool registry `register_epic_tool` / `epic_tools` / `clear_epic_tools` in `cascade/epic/registry.py`; `invoke_tool` records success as a role=`tool` message.
- `boot_epic` + `install_epic_boot_hook(root)` register feat_002 `register_boot_hook("epic", ...)` idempotently; boot reads the epic doc, ensures graph, and calls `ingest_queue`. No auto-import from `cascade` or `cascade.watchdog`.
- `pyproject.toml` lists `langgraph` and `langgraph-checkpoint-sqlite` runtime dependencies.
- `tests/epic/test_runtime.py` covers checkpoint persistence, one-turn roles, queue idempotency, boot hook, tools, and isolated epic state.

## Files likely touched

- `cascade/epic/__init__.py`
- `cascade/epic/state.py`
- `cascade/epic/checkpoint.py`
- `cascade/epic/graph.py`
- `cascade/epic/boot.py`
- `cascade/epic/registry.py`
- `tests/epic/test_runtime.py`
- `pyproject.toml`

## Implementation notes

Graph id is the epic work id (e.g. `epic_001`), matching queue dest from `activate_epic`. Cache SQLite connections per checkpoint path. Store repo `root` on `install_epic_boot_hook(root)` so `boot_epic(work_id)` matches the hook signature. Role nodes quote or name the latest human/event content deterministically.

## Skills

_(none)_

## Test plan

- `python3 -m pytest tests/epic/test_runtime.py -q`
- `python3 -m pytest tests/watchdog/test_hooks.py tests/watchdog/test_dispatch.py -q` (no hook auto-registration on import)

## Out of scope

- `mint_feature`, `tool_guard`, `record_decision`, comments, amendments
- War Room route changes
- Moving feat_004 or editing epic_001
- Git commit
