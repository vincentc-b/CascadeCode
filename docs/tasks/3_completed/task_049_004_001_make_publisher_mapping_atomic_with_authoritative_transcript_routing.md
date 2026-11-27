---
id: task_049_004_001
title: Make publisher mapping atomic with authoritative transcript routing
tier: task
status: completed
parent: feat_049_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: e5ef117aa226db5cc1211af520d892432cc0ae53
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Make publisher mapping atomic with authoritative transcript routing

## Parent Feature

[feat_049_004](../../features/2_active/feat_049_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope
Complete the routing freshness correction in `cascade/recovery_progress/publisher.py` and the smallest necessary `cascade/war_room/chat_store.py` source lookup. Start from the integrated candidate code already present in the Feature checkout. Preserve v1 public routes, receipt/entry/graph/message identities and writer budgets.

## Acceptance criteria
- Every mapping writer—`publish_committed_transition`, `drain_recovery_progress`, `record_transcript_milestone` and the shared private helper—uses an authoritative source-key acknowledgement under the stable graph OS fence, held until the publisher SQLite mapping and entry-reference transaction commits. Apply this to first insertion and existing-row refresh. A stale saved acknowledgement cannot downgrade routing.
- Enforce one lock order: publisher process lock and SQLite write transaction before graph fence. Inspect all relevant callers and room-move owner callbacks; prevent inverse acquisition. Avoid unbounded repair/import/publication while the publisher transaction is held. Pending/missing/conflicting source evidence retains existing mapping or replay eligibility and does not fabricate routing.
- Preserve receipt_id, entry_id, graph_id and message_id conflict rejection, exactly one recovery line, unchanged recovery admission, bounded fast path and fair drain. Existing index and publisher SQLite provide restart state; no incarnation ordering assumption or new public token.
- Deterministic real fast-path or drain interleaving pauses an old acknowledgement, rewrites or moves the room, commits current mapping, then resumes the old writer. Verify saved current routing, stable receipt/message IDs and one line. Cover public check-to-write race, first insertion, restart/replay, genuine identity conflict and unavailable/pending source; do not advance a replay cursor past undelivered mapping.
- Run focused `tests/recovery_progress/test_transcript_milestones.py`, `tests/recovery_progress/test_publisher.py` and affected `tests/war_room/test_durable_chat_store.py` cases. Record actual commands/results and measured writer cost in task closeout.

## Design impact
Reconcile `cascade/watchdog/DESIGN.md`, `cascade/war_room/DESIGN.md` and affected source-linked `cascade-watchdog-code`/`cascade-dashboard-code` relationships against the implementation. Provide Task 3 the exact changed symbols, normal/delayed/restart traces and any material documentation gap. Current-design prose only; do not attribute architecture to delivery IDs.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
