---
id: task_012_002_002
title: Emit durable deduplicated convergence diagnostics
tier: task
status: completed
parent: feat_012_002
children: []
depends_on:
- task_012_002_001
owners:
- swe
skills: []
parent_rev: 87e25c54c4ac798175399a62184d316494d5fc2b
created: '2026-10-23'
updated: '2026-10-23'
---
# Emit durable deduplicated convergence diagnostics

## Parent Feature

[feat_012_002](../../features/2_active/feat_012_002.md)

## Depends on

- task_012_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Publish convergence-stall findings into the existing durable event/toast stream.

## Scope

- Consume the detector output from task_012_002_001.
- Include the affected work item, observed blocker, threshold, and timing evidence.
- Deduplicate repeated polls while the relevant evidence is unchanged.
- Allow a new diagnostic when evidence materially changes or a recovered item stalls again.
- Preserve read-only behavior toward live work and all dispatch gates.

## Acceptance

- A newly stalled eligible item produces one durable diagnostic.
- Unchanged evidence does not produce a diagnostic every poll.
- Changed blocker/timing evidence or a stall after recovery can produce a fresh diagnostic.
- Diagnostic payloads are sufficient for War Room investigation and persist through the established stream.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
