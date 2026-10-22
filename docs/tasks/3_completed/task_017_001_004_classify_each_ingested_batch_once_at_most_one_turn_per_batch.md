---
id: task_017_001_004
title: Classify each ingested batch once; at most one turn per batch
tier: task
status: completed
parent: feat_017_001
children: []
depends_on:
- task_017_001_003
owners:
- swe
skills: []
parent_rev: abed68d27ed9ada4fe1a1ef7ca87fbd3ff794881
created: '2026-10-22'
updated: '2026-10-22'
---
# Classify each ingested batch once; at most one turn per batch

## Parent Feature

[feat_017_001](../../features/2_active/feat_017_001.md)

## Depends on

- task_017_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Inside the delivery job, classify each ingested batch exactly once. Human CommentPosted and CommentReplied events are staged as human messages. Other non-comment events are staged as event messages. Agent-authored replies and CommentResolved schedule nothing. If anything was staged, the batch runs at most one model turn; otherwise it runs none. Preserve queue order in the staged messages. Acceptance (system-level, counting fake turn runner): one human comment yields exactly one turn; an agent reply or CommentResolved yields zero turns; message order matches queue order.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
