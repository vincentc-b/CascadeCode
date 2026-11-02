---
id: task_012_003_001
title: Build the disposable probe workspace harness
tier: task
status: completed
parent: feat_012_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 117f8b8cb86ebb3794cf09308c0ccc4e72215cf1
created: '2026-10-23'
updated: '2026-10-23'
---
# Build the disposable probe workspace harness

## Parent Feature

[feat_012_003](../../features/2_active/feat_012_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Implement the probe entry point and lifecycle for a temporary git repository and Cascade board.

## Acceptance criteria

- Creates all probe state beneath a newly allocated temporary workspace.
- Rejects or structurally excludes live-board paths as mutation targets.
- Applies bounded execution controls and supports safe repeated runs.
- Cleans up by default, with artifact retention available only through an explicit debug option.
- Introduces no daemon, hosted service, or always-on canary.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
