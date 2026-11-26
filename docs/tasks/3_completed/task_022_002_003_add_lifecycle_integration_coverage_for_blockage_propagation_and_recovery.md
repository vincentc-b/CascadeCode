---
id: task_022_002_003
title: Add lifecycle integration coverage for blockage propagation and recovery
tier: task
status: completed
parent: feat_022_002
children: []
depends_on:
- task_022_002_002
owners:
- swe
skills: []
parent_rev: 404fe156773f0a2b39ef5ba640e96d34bc7e25f4
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
---
# Add lifecycle integration coverage for blockage propagation and recovery

## Parent Feature

[feat_022_002](../../features/2_active/feat_022_002.md)

## Depends on

- task_022_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal integration tests covering: unresolved child propagation; task → feature → epic visibility across sweeps; machine-readable origin/reason provenance; concurrent or already-applied transitions; manual-state and terminal-work safety; recovery clearing of only the matching monitoring-derived cause; and preservation of unrelated manual and sibling blocker causes. Prefer end-to-end lifecycle assertions over redundant mock-heavy unit tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
