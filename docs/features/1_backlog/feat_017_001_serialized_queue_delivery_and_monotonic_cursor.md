---
id: feat_017_001
title: Serialized queue delivery and monotonic cursor
tier: feature
status: backlog
parent: epic_017
children:
- task_017_001_001
- task_017_001_002
- task_017_001_003
- task_017_001_004
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: 40103cc528f3c15f90c6c0131d77d7b8b18ac6e2
created: '2026-10-22'
updated: '2026-10-22'
provider: cursor
models:
  feature_lead: claude-opus-5-5
  feature_architect: claude-opus-5-5
approved_at: '2026-10-22T22:14:46.331172+00:00'
---
# Serialized queue delivery and monotonic cursor

## Parent Epic

epic_017

## Intent

Stop the duplicate-turn loop. Queue ingestion for epic, feature, and task graphs runs only inside the serialized per-graph kickoff job under `_graph_lock`, so a running `graph.invoke` can no longer overwrite the advanced `last_queue_offset` or the ingested event messages.

## Scope

- The watchdog (`deliver_queue_kickoffs`, `kickoff_graph_queue_event`) no longer calls `ingest_queue` directly. It submits a delivery job when the queue file is ahead of the checkpoint cursor.
- At most one pending delivery job per graph. After a turn, the job re-checks the queue once so events that arrived mid-turn get exactly one follow-up.
- Each batch is classified once. Human CommentPosted/CommentReplied events are staged as human messages; non-comment events are staged as event messages; agent replies and CommentResolved schedule nothing. A batch runs at most one model turn.
- A single cursor-write helper refuses to lower the cursor. The only exception is the explicit, logged reset when `read_events` detects a truncated or replaced file.
- No change to queue format or checkpoint schema.

## Acceptance (system-level tests with a counting fake turn runner)

- First task: write a failing reproduction of an append during a blocked in-flight turn that shows the lost cursor and lost messages.
- After the fix: that event is ingested once and the cursor ends at EOF.
- N maintenance ticks on an unchanged queue start zero turns.
- One human comment yields exactly one turn.
- An agent reply or CommentResolved yields zero turns.
- Message order matches queue order.

## Out of scope

Restart resume behavior and stall warnings (next feature).

## Data structures

TBD.

## API contracts

TBD.

## Logic flow

```mermaid
flowchart TD
  A[Start] --> B[End]
```

## Task breakdown

Dependency order; each task carries the acceptance tests for the behavior it delivers.

- task_017_001_001 — Failing reproduction: append during blocked in-flight turn loses cursor and messages (completed, merged)
- task_017_001_002 — Monotonic cursor-write helper (depends on 001; completed, merged)
- task_017_001_003 — Serialize queue ingestion inside per-graph kickoff job under `_graph_lock`; one pending job per graph; post-turn re-check (depends on 001, 002; completed, merged)
- task_017_001_004 — Classify each ingested batch once; at most one turn per batch (depends on 003; active)

## Risks & upward questions

None.

## Decision log

None yet.

## Closeout

Completed child work: `task_017_001_001` (Failing reproduction: append during blocked in-flight turn loses cursor and messages), `task_017_001_002` (Monotonic cursor-write helper), `task_017_001_003` (Serialize queue ingestion inside per-graph kickoff job under _graph_lock), `task_017_001_004` (Classify each ingested batch once; at most one turn per batch).
