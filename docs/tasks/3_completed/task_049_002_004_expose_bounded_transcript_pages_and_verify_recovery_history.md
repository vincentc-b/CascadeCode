---
id: task_049_002_004
title: Expose bounded transcript pages and verify recovery history
tier: task
status: completed
parent: feat_049_002
children: []
depends_on:
- task_049_002_001
- task_049_002_002
- task_049_002_003
owners:
- swe
skills: []
parent_rev: f17df9e7c9503eeb2411111fb3461775eb1b62c6
created: '2026-11-25'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose bounded transcript pages and verify recovery history

## Parent Feature

[feat_049_002](../../features/2_active/feat_049_002_persist_recovery_milestones_and_bounded_transcript_history.md)

## Depends on

- task_049_002_001
- task_049_002_002
- task_049_002_003

## Acceptance criteria

publish immutable graph pages from committed offsets and direct pointer; implement GET /api/transcript/v1/<graph_id> with direction=older|after, opaque graph/incarnation/direction/sequence/high-water cursor, default 50/max 100, 1 MiB source and 256 KiB serialized budgets. Keep /api/chat/<graph_id> latest-window array with Link rel=next to older versioned page and X-Transcript-Completeness/Incarnation/Has-More; typed 400 invalid_request, 409 cursor_restart and 503 history_pending/transcript_unavailable. Oversize legacy rows have labeled bounded preview and chunk-detail continuation, no silent deletion. No GET index creation, full JSONL scan, checkpoint, write or provider/Git/process probe. Focused API/integration and real-browser fixture cover incremental poll/load older, cursor move/rewrite/overflow, large history, unknown times, missed receipt/restart and the epic_044 held-turn start milestone. Reconcile DESIGN.md, cascade/DESIGN.md, owning War Room/Task/Watchdog/Workspace designs, model.dsl/views.dsl/workspace.contract.json; validate/render, context-to-Code/Level up/deep link/pinned source, stale symbols, warm reuse and render bounds; record measured results and limitations.

### Oversized legacy detail contract

Freeze `GET /api/transcript/v1/<graph_id>/items/<message_id>/detail?cursor=<opaque>` before dependent UI handoff. A bounded preview item sets `detail_truncated:true`, `detail_url` and `detail_cursor`; the detail response contains `schema_version:1`, exact `graph_id`, `message_id`, `incarnation`, `encoding:"utf-8"`, a UTF-8-aligned `chunk` of at most 64 KiB, `next_cursor` and `complete`. The cursor binds graph, incarnation, message ID, immutable detail digest and byte offset. Read only the requested immutable chunk through the same no-follow pointer and manifest; no caller-supplied path, JSONL scan, writer SQLite or GET repair. Invalid cursor is 400 `invalid_request`, changed incarnation/digest is 409 `cursor_restart` with restart metadata, unavailable detail is 503 `history_pending`. Enforce the 1 MiB aggregate source and 256 KiB serialized response caps for this route too. Test multi-chunk reconstruction, UTF-8 boundaries, stale/foreign cursors, missing chunks and preview honesty. Include this route in final Feature 3 contract fixtures and verify the War Room design plus native cascade-dashboard-code route/reader symbols against source.

Task 1 crash repair is owned by task_049_002_005. Final API acceptance must exercise its full-tail fsync replay and resumable room movement across copy, source removal, owner switch and index/incarnation reset, including terminal retirement and split roots. Also fault-inject process death after rollback or legacy-label JSONL replacement but before SQLite index/incarnation reset; restart must preserve the authoritative history, retained source keys and routable writes without GET repair. Do not sign off on Task 1's original content-only replay test as durability evidence.

## Files likely touched

cascade/war_room/sidecar_routes.py and server.py, bounded transcript reader/pages, tests/war_room/; root and affected child designs; model.dsl, views.dsl, workspace.contract.json.

## Implementation notes

Follow the saved feature storage/API contract and completed producer fixtures. Record design review and verification evidence in Task closeout.

## Skills

_(none)_

## Test plan

Loopback API and Chromium journey with large history, older/after cursors, typed errors, read-only instrumentation, held-turn milestone, source contract/render/navigation checks.

## Out of scope

New recovery scheduler, repair authority, paid model turn, unbounded GET scan and unrelated UI redesign.
