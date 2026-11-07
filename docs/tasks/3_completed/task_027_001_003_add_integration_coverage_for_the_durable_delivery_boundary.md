---
id: task_027_001_003
title: Add integration coverage for the durable delivery boundary
tier: task
status: completed
parent: feat_027_001
children: []
depends_on:
- task_027_001_002
owners:
- swe
skills: []
parent_rev: 8cba6581131aba3a53994eb8900a7dda871d6be9
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Add integration coverage for the durable delivery boundary

## Parent Feature

[feat_027_001](../../features/2_active/feat_027_001.md)

## Depends on

- task_027_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal integration coverage for the complete delivery contract.

Required scenarios:
- Drain/restart after the deliverable commit but before final validation completes.
- Drain/restart after successful validation but before downstream processing completes.
- Red final validation does not queue a merge or emit ready.
- Deliverable SHA or Feature-base SHA changes force revalidation and use the new evidence.
- Replay/retry does not create duplicate merge queue entries.

Acceptance:
- Tests exercise the real persistence/queue/state-transition integration path with minimal mocking.
- Each scenario asserts both durable queue state and externally visible Task state/events.
- Coverage avoids redundant lower-level tests already exercised by these integration cases.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
