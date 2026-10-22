---
id: task_017_002_002
title: Stall and duplicate-kickoff detection with deduplicated warning and War Room note
tier: task
status: completed
parent: feat_017_002
children: []
depends_on:
- task_017_002_001
owners:
- swe
skills: []
parent_rev: ead4def40b2a11c15378ac61a86f7050bef300ed
created: '2026-10-22'
updated: '2026-10-22'
---
# Stall and duplicate-kickoff detection with deduplicated warning and War Room note

## Parent Feature

[feat_017_002](../../features/2_active/feat_017_002.md)

## Depends on

- task_017_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Goal
Make a non-advancing cursor or a duplicate kickoff visible before it turns into a loop.

## Scope
- Stall: during each watchdog maintenance pass, flag a graph whose queue stays ahead of its cursor across consecutive passes (at least 2) while no turn is running.
- Duplicate kickoff: in the serialized delivery path from task_017_002_001, flag a kickoff that targets a batch offset already delivered.
- Each incident emits exactly one structured log warning and one War Room system note. Deduplicate per `(work_id, offset)` with in-memory state on the supervisor. No persistence is needed; re-warning once after a restart is acceptable.
- Reuse the existing War Room system-note mechanism. Do not add a new channel.

## Acceptance (system-level test)
- Force a stall (pending queue lines, no turn running, delivery suppressed), then run repeated maintenance ticks. Exactly one log warning and one War Room note are emitted.

## Out of scope
Auto-remediation, dashboards, metrics backends, and watchdog performance work.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
