---
id: task_022_001_003
title: Verify supervisor health and remediation acceptance scenarios
tier: task
status: completed
parent: feat_022_001
children: []
depends_on:
- task_022_001_002
owners:
- swe
skills: []
parent_rev: d27fd359c1991f129ef13fd64c0d3282de81d8c0
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
---
# Verify supervisor health and remediation acceptance scenarios

## Parent Feature

[feat_022_001](../../features/2_active/feat_022_001.md)

## Depends on

- task_022_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal integration coverage through the real supervisor lifecycle and persisted status model. Demonstrate: healthy child is a no-op; one eligible unchanged incident triggers exactly one authorized recovery attempt; a successful attempt returns the child to the expected canonical state; terminal reports and terminal supervisors are excluded; repeated and concurrent sweeps are idempotent for the same child identity and observed state/version; and transient inspection/recovery failure is handled safely without duplicate or unlimited retries. Reuse lower-level coverage where the integration scenarios already exercise behavior; avoid redundant mock-heavy unit tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
