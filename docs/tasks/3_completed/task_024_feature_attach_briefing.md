---
id: task_024
title: Feature attach, briefing pack, and war-room wiring
tier: task
status: completed
parent: feat_005
children: []
depends_on:
  - task_020
  - task_023
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Feature attach, briefing pack, and war-room wiring

## Parent Feature

[feat_005](../../features/3_completed/feat_005_feature_team.md) — Feature Team, comments, and drop-in.

## Depends on

- task_020 — scoped reads for doc, parent epic @ `parent_rev`, children
- task_023 — open comment threads from sidecar store

## Acceptance criteria

- `BriefingPack` builder (e.g. `cascade/feature/briefing.py`) returning: `doc` (`WorkDoc`), `decision_log` excerpt (string slice of `## Decision log`), `open_comments` (open threads for this feature’s `doc_id`), `parent_constraints` (`WorkDoc | null` for parent epic at `parent_rev`), `recent_messages` (last N messages from **this feature graph only** via checkpointer state, not epic war-room sidecar).
- `briefing_pack_to_dict` in `cascade/war_room/serialize.py` replaces `briefing_stub_to_dict` for feature (and epic if straightforward); attach response matches feat_005 API shape.
- `POST /api/attach` returns real briefing pack for feature ids; emits `HumanAttached { graph_id, tier }` on the appropriate queue(s) per DESIGN §8.
- `POST /api/detach` emits `HumanDetached`.
- `cascade/feature/wiring.py`: `load_feature_tools()` imports mint, decisions, docs, comments, amendment stub modules idempotently; `accept_human_chat` calls `ingest_human` for **feature-tier** work ids only (epic path remains in epic wiring).
- `POST /api/chat/{feature_id}` ingests into the feature graph; messages do **not** appear in the epic graph transcript or `docs/_war_room/chat/epic_*.jsonl` conflation — feature chat sidecar remains per `graph_id`.
- `WarRoomHTTPServer` calls `load_feature_tools()` after root is set (mirror epic).
- `tests/feature/test_briefing.py` and `tests/feature/test_chat_wire.py` cover attach payload, detach events, feature ingest isolation from epic checkpoint, and cross-graph non-leakage.

## Files likely touched

- `cascade/feature/briefing.py`
- `cascade/feature/wiring.py`
- `cascade/war_room/serialize.py`
- `cascade/war_room/sidecar_routes.py`
- `cascade/feature/__init__.py` (exports without eager tool imports)
- `tests/feature/test_briefing.py`
- `tests/feature/test_chat_wire.py`

## Implementation notes

Attachment state remains `AttachmentState` (multi-attach allowed). Recent messages: read from LangGraph state for `feature_id`, cap N (e.g. 20). Epic attach may keep stub or minimal pack — scope is feature room parity with feat_003 epic chat routes, not a new UI framework.

## Skills

_(none)_

## Test plan

- `python3 -m pytest tests/feature/test_briefing.py tests/feature/test_chat_wire.py -q`
- `python3 -m pytest tests/epic/test_chat_wire.py -q` (epic path still passes)

## Out of scope

- Comment store internals (task_023)
- Graph runtime boot (task_018)
- `propose_epic_amendment` behavior beyond registration in load path (task_025)
