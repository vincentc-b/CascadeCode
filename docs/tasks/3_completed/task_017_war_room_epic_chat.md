---
id: task_017
title: War Room epic chat enters the graph
tier: task
status: completed
parent: feat_004
children: []
depends_on: [task_012, task_014, task_015, task_016]
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-10
---

# War Room epic chat enters the graph

## Parent Feature

[feat_004](../../features/3_completed/feat_004_epic_team.md) — Epic Team graph.

## Depends on

- task_012 — epic graph runtime and checkpointer
- task_014 — `mint_feature` / `list_children`
- task_015 — `record_decision`
- task_016 — comment/amendment stubs

## Acceptance criteria

- `load_epic_tools()` imports mint, decisions, and stubs so epic tools register; safe to call repeatedly.
- `accept_human_chat(graph_id, message, root=...)` ingests into `ingest_human` only when `graph_id` is an existing epic-tier work doc; feature and unknown ids are no-ops.
- `POST /api/chat/{graph_id}` after a successful sidecar append calls `accept_human_chat` inside try/except so non-epic chats and graph failures still return HTTP 202 with the sidecar payload.
- `WarRoomHTTPServer` installs `install_epic_boot_hook(self.root)` and `load_epic_tools()` after `self.root` is set.
- `cascade.epic` exports `load_epic_tools` and `accept_human_chat` without importing tool modules at package import time.
- `tests/epic/test_chat_wire.py` covers epic graph state after POST, feature id without checkpoint, tool registration, `mint_feature` via `invoke_tool`, and `reply_comment` raising `EpicToolUnavailable`.

## Files likely touched

- `cascade/epic/wiring.py`
- `cascade/epic/__init__.py`
- `cascade/war_room/sidecar_routes.py`
- `cascade/war_room/server.py`
- `tests/epic/test_chat_wire.py`

## Implementation notes

Map sidecar `message["body"]` to graph human `content`. Pass through optional `id` and `ts`. HTTP handler swallows graph exceptions; direct calls to `accept_human_chat` propagate. Boot hook idempotency for the same root remains in `boot.py`; changing root updates `_boot_root` without double-registering the hook.

## Skills

_(none)_

## Test plan

- `python3 -m pytest tests/epic tests/war_room -q`

## Out of scope

- LLM-backed manager/architect nodes
- Comment store and amendment workflows (feat_005 / feat_006)
- Editing feat_004 or epic_001 feature docs
- Git commit
