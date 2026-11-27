---
id: task_049_003_002
title: Render durable Historical transcript pages and recovery milestones
tier: task
status: completed
parent: feat_049_003
children: []
depends_on:
- task_049_003_001
owners:
- swe
skills: []
parent_rev: be5dfdba819e21143dff12ef2aafdb5403aa6246
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Render durable Historical transcript pages and recovery milestones

## Parent Feature

[feat_049_003](../../features/2_active/feat_049_003.md)

## Depends on

- task_049_003_001

## Acceptance criteria

- Bind page, detail, legacy-header and typed error behavior to `tests/war_room/test_transcript_pages_api.py::test_typed_invalid_restart_pending_and_get_is_projection_only` and `::test_oversized_detail_reconstructs_utf8_and_rejects_foreign_or_stale_cursor` on Feature 4 handoff `a3d4a42b3df92a553206c300c42142600183eaef`; incomplete detail chunks advance UTF-8 byte offsets positively and reconstruct exact text.
- Use `tests/recovery_progress/test_transcript_milestones.py` for committed mapping and `tests/war_room/test_durable_chat_store.py::test_fenced_source_lookup_leaves_pending_intent_for_writer_repair` for pending evidence. Keep progress revision distinct from transcript incarnation and reject stale graph/incarnation responses.
- Diagram impact: inspect `cascade-war-room-components`, `cascade-dashboard-code` and affected `cascade-war-room-http-code` source symbols, source contract and War Room design; give context/container no-change reasons grounded in the diff. Preserve producer ownership in `cascade/recovery_progress/DESIGN.md`.

- Use versioned latest, older and after transcript pages with stable graph/incarnation/message identity; preserve older high-water and scroll under appends.
- Render System · Recovery milestones separately from authored manager/architect and human messages; preserve older dated claims, nullable occurrence and provenance.
- Resolve only committed milestone_refs; show pending delivery, incomplete import and history_pending.
- Provide keyboard access, safe local links and bounded preview/detail continuation; refuse wrong graph, stale incarnation/detail and late responses without mixing history.
- Reconcile War Room design and affected Dashboard Code nodes with real declarations, source contract and normal/failure flow.

## Files likely touched

cascade/war_room/static/war_room.js; War Room template/style; cascade/war_room/DESIGN.md; architecture model/views/contract only if actual symbols change.

## Implementation notes

Implement Task 2 in the feature spec: versioned latest/older/after pages, stable anchors, System · Recovery and authored distinctions, scroll/keyboard behavior, pending/import states, bounded detail continuation, graph/incarnation/cursor refusal, focused UI tests, and War Room/Dashboard Code updates.

## Skills

_(none)_

## Test plan

Focused transcript API/Chromium navigation and detail cursor cases; no redundant micro-tests.

## Out of scope

No producer ledger or recovery authority changes.
