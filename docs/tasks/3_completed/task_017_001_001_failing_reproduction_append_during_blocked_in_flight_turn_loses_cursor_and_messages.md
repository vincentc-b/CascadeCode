---
id: task_017_001_001
title: 'Failing reproduction: append during blocked in-flight turn loses cursor and messages'
tier: task
status: completed
parent: feat_017_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 8abd2d65b25f6f1f9f090d5f88bc16567c5fe64e
created: '2026-10-22'
updated: '2026-10-22'
---
# Failing reproduction: append during blocked in-flight turn loses cursor and messages

## Parent Feature

[feat_017_001](../../features/2_active/feat_017_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add a system-level test harness with a counting fake turn runner that can block mid-turn. Reproduce: start a turn for a graph, block it, append an event to the queue, let the watchdog (deliver_queue_kickoffs / kickoff_graph_queue_event) run, then release the turn. Assert the bug as it stands today: last_queue_offset is overwritten back to the old value and the ingested event messages are lost, so the event is re-delivered and causes a duplicate turn. Mark the expected-correct assertions (event ingested once, cursor at EOF) as xfail/failing so later tasks flip them green. The harness is reused by all later tasks. No production code changes.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
