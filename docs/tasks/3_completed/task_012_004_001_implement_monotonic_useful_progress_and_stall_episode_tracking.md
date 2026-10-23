---
id: task_012_004_001
title: Implement monotonic useful-progress and stall episode tracking
tier: task
status: completed
parent: feat_012_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 529f4f0405c3f810a7c180c63a004b2b19588d85
created: '2026-10-23'
updated: '2026-10-23'
---
# Implement monotonic useful-progress and stall episode tracking

## Parent Feature

[feat_012_004](../../features/2_active/feat_012_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the minimal watchdog state model for an in-flight SWE turn.

Acceptance:
- Track transport/process liveness separately from useful progress.
- Count only provider events, completed tool calls, checkpoint advancement, and task-worktree file/content advancement as useful progress.
- Timestamp evidence with an injected monotonic clock and reduce it to a stable episode signature.
- Apply a configurable bounded no-progress deadline.
- New useful progress creates a new episode; repeated observation of unchanged evidence retains the same episode.
- Do not treat lease renewal, a connected transport, or a pending provider await as progress.
- Add focused clock-driven tests for deadline boundaries and episode identity.

Constraint:
- Do not implement a competing cancellation path; the feature must ultimately use the feat_018_002 cancellation/draining seam.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
