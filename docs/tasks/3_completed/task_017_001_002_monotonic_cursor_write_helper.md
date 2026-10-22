---
id: task_017_001_002
title: Monotonic cursor-write helper
tier: task
status: completed
parent: feat_017_001
children: []
depends_on:
- task_017_001_001
owners:
- swe
skills: []
parent_rev: 826dc49f8f6cf9848bcc70596c594b08d5f269aa
created: '2026-10-22'
updated: '2026-10-22'
---
# Monotonic cursor-write helper

## Parent Feature

[feat_017_001](../../features/2_active/feat_017_001.md)

## Depends on

- task_017_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add a single helper that all writes of last_queue_offset go through. It refuses to lower the cursor (no-op plus a warning log). The only exception is an explicit, logged reset path used when read_events detects a truncated or replaced queue file. Route every existing cursor write through it. No change to queue format or checkpoint schema. Tests: a small test that a lower write is refused and a truncation reset is allowed and logged, using the harness from the reproduction task.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
