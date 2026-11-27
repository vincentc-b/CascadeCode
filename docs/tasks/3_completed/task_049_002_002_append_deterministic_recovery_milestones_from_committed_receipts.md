---
id: task_049_002_002
title: Append deterministic recovery milestones from committed receipts
tier: task
status: completed
parent: feat_049_002
children: []
depends_on:
- task_049_002_001
owners:
- swe
skills: []
parent_rev: ac9ddcf32cd67965da38682847f59e183f78b1d7
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Append deterministic recovery milestones from committed receipts

## Parent Feature

[feat_049_002](../../features/2_active/feat_049_002_persist_recovery_milestones_and_bounded_transcript_history.md)

## Depends on

- task_049_002_001

## Acceptance criteria

consume unchanged Feature 1 receipt_id/entry_id and safe v1 fields; create one concise System · Recovery line per retained receipt, preserving action/generation/attempt/transition sequence, nullable occurrence, direct/reconciled/legacy provenance, safe target/source reference. Publish after authoritative action/incident commit and before long executor completion; never derive progress from a model or observation timestamp. Bounded startup/early watchdog drain (100 receipts/owners or one second) replays missed notification, source-committed/chat-missing and chat-committed/cursor-not-advanced; fair continuation, lag and empty milestone_refs until durable chat commit. Source acknowledgement after graph fence release; chat failure never changes repair admission. Cover duplicate receipts, distinct repeated stages, failure/wait/publication/independent verified completion, hold final reply, restart and split roots. Reconcile Task/Watchdog/Workspace/War Room designs and cascade-task-code, cascade-watchdog-code, cascade-workspace-code, cascade-dashboard-code and component ancestors with actual symbols and flows.

### Durable receipt acknowledgement and publisher refs

Own `append_committed_recovery_receipt(root, receipt, snapshot)` after authoritative source commit and source-lock release. It returns a committed acknowledgement `{receipt_id, entry_id, graph_id, message_id, incarnation, append_sequence}` or typed pending. The graph-index receipt key and exact JSONL offset survive append-before-ack restart; replay by receipt_id returns the same message ID. Only after releasing the graph fence, call `recovery_progress.publisher.record_transcript_milestone(root, ack)` to durably map receipt_id to entry_id/message_id in the producer writer index, mark affected aliases dirty and republish. `_upsert` joins committed mappings for retained receipt_refs into ordered milestone_refs, preserving them across later entry updates. A crash before publisher mapping or source-cursor acknowledgement replays the graph acknowledgement without duplicate JSONL and retries publisher mapping; source cursor advances only after both durable commits. Unknown/unsafe target, ambiguous graph or missing evidence stays pending with empty refs. Never take a source-ledger lock under the graph fence and never repair on GET.

Pin producer feat/feat_049_001 revision dc47068cebf5643c319d37785edf35882fb96941; verify receipt identity against `cascade/watchdog/incidents.py::transition_receipt_v1`, entry identity and safe fields against `cascade/recovery_progress/publisher.py::_entry_id/_derive_entry`, and response shape against `tests/war_room/fixtures/recovery_progress_v1_epic_044.json`, `tests/war_room/test_recovery_progress_api.py` and `tests/war_room/test_http_read.py`. Preserve success entry_count, entry schema_version/entry_revision, pending without entry_count, and both revision fields on 409. Update the publisher-side cascade-watchdog-code view and Watchdog/War Room design interface; the cascade/recovery_progress child-design ownership gap remains routed to the producer owner.

## Files likely touched

cascade/war_room/ transcript consumer; cascade/recovery_progress/ publisher integration; cascade/watchdog/ supervised drain; cascade/task/ receipt handoff; tests/recovery_progress/ and tests/war_room/; owning designs and architecture source.

## Implementation notes

Follow the saved feature storage/API contract and completed producer fixtures. Record design review and verification evidence in Task closeout.

## Skills

_(none)_

## Test plan

Focused integration with actual committed Task/Watchdog receipts and held executor; duplicate notification, missed transition, fair replay, provenance and reference mapping.

## Out of scope

New recovery scheduler, repair authority, paid model turn, unbounded GET scan and unrelated UI redesign.
