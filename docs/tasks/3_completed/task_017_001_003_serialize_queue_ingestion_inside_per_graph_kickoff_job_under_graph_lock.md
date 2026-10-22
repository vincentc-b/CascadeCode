---
id: task_017_001_003
title: Serialize queue ingestion inside per-graph kickoff job under _graph_lock
tier: task
status: completed
parent: feat_017_001
children: []
depends_on:
- task_017_001_001
- task_017_001_002
owners:
- swe
skills: []
parent_rev: 826dc49f8f6cf9848bcc70596c594b08d5f269aa
created: '2026-10-22'
updated: '2026-10-22'
---
# Serialize queue ingestion inside per-graph kickoff job under _graph_lock

## Parent Feature

[feat_017_001](../../features/2_active/feat_017_001.md)

## Depends on

- task_017_001_001
- task_017_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Applies to epic, feature, and task graphs. The watchdog (deliver_queue_kickoffs, kickoff_graph_queue_event) stops calling ingest_queue. Instead it compares the queue file end against the checkpoint cursor and, if the queue is ahead, submits a delivery job. At most one pending delivery job per graph (dedupe on submit). The job takes _graph_lock, runs ingest_queue plus the turn, and writes the cursor through the monotonic helper. After the turn it re-checks the queue once, so events that arrived mid-turn get exactly one follow-up. Acceptance: the reproduction test passes (event ingested once, cursor ends at EOF), and N maintenance ticks on an unchanged queue start zero turns.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
