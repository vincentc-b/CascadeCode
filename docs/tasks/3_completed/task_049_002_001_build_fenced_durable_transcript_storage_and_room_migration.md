---
id: task_049_002_001
title: Build fenced durable transcript storage and room migration
tier: task
status: completed
parent: feat_049_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 1de33f553c76c21ded734453d8855d6a4f6bbc02
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Build fenced durable transcript storage and room migration

## Parent Feature

[feat_049_002](../../features/2_active/feat_049_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implementation acceptance: preserve owning JSONL as authority; add tracking-root graph OS lock shared by append/remove/sync/move writers, SQLite unique source/message key and offset index, durable exact-line intent, fsync-before-index commit and acknowledgement after fence release. Repair only matching empty/complete/partial intended tail; unexpected bytes or uncertain owner remain pending without unrelated truncation. Room dispatch/completion and split roots move/copy under fence and change incarnation. Resumable 1 MiB/100-row legacy import retains IDs/append time and null source occurrence. No source lifecycle lock under graph fence; no new scheduler or repair authority. Exercise two real processes, crash at intent/partial append/fsync/index/room-move boundaries, legacy/torn JSONL and no duplicate or lost unrelated bytes. Update cascade/war_room/DESIGN.md and routing owner designs; synchronize cascade-dashboard-code and affected cascade-workspace-code/model/views/contract with real symbols; trace normal and crash recovery.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
