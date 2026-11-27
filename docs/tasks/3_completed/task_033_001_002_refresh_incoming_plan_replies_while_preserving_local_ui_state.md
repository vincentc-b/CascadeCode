---
id: task_033_001_002
title: Refresh incoming plan replies while preserving local UI state
tier: task
status: completed
parent: feat_033_001
children: []
depends_on:
- task_033_001_001
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
# Refresh incoming plan replies while preserving local UI state

## Parent Feature

[feat_033_001](../../features/2_active/feat_033_001.md)

## Depends on

- task_033_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Using the inspected shared comment path and existing API/event IDs, refresh replies for Epic and Feature plans in inline and tray placements. Target visibility within 5 seconds of successful API availability on visible connected pages. Allow no overlapping requests or accumulated timers; pause periodic reads while hidden, refresh on visibility/reconnect, retain last successful data on failures, and retry with capped backoff. Discard stale responses after navigation/unmount. Update comment state without remounting the plan or losing drafts, focus/open controls, scroll position, placement, or resolved/outdated styling. Refresh reads must never post comments or dispatch turns. Preserve existing API/storage and posting contracts; escalate any required contract change.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
