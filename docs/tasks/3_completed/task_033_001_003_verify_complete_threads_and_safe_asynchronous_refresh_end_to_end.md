---
id: task_033_001_003
title: Verify complete threads and safe asynchronous refresh end to end
tier: task
status: completed
parent: feat_033_001
children: []
depends_on:
- task_033_001_001
- task_033_001_002
owners:
- swe
skills: []
parent_rev: 0fb07a1547a7f0d94ac19c5448d55c002bac3b84
created: '2026-11-05'
updated: '2026-11-05'
provider: codex
flex_mode: false
models:
  swe: gpt-6.1-sol
---
# Verify complete threads and safe asynchronous refresh end to end

## Parent Feature

[feat_033_001](../../features/2_active/feat_033_001.md)

## Depends on

- task_033_001_001
- task_033_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Use the existing browser harness and a compact matrix covering Epic/Feature plans and inline/tray placements. Regress epic_028 chains cmt_001 → cmt_006 → cmt_007 and cmt_001 → cmt_008 → cmt_009/cmt_010 on initial load and asynchronous arrival. Cover deep nesting, malformed/missing parents, deterministic ordering and exactly-once visibility. Verify drafts, focus/open controls, scroll, placement, and resolved/outdated styling survive updates. Exercise bounded request timing, hidden pause, visibility/reconnect, failures/backoff, no overlap/timer accumulation, and stale responses after navigation/unmount. Reuse posting/queue regressions to verify one human post produces exactly one event and one owning-team kickoff, while repeated refresh/reconnect produces none. Add only missing high-signal cases; no redundant test pyramid or new framework. Record commands/results and any limitations in the task.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
