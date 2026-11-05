---
id: task_027_003_003
title: Add end-to-end coverage for scoped recovery behavior
tier: task
status: completed
parent: feat_027_003
children: []
depends_on:
- task_027_003_002
owners:
- swe
skills: []
parent_rev: ebaa4bba43f2a63bb0492a08d4cfe39d67b2ca90
created: '2026-10-31'
updated: '2026-10-31'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Add end-to-end coverage for scoped recovery behavior

## Parent Feature

[feat_027_003](../../features/2_active/feat_027_003.md)

## Depends on

- task_027_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add focused integration or API-level coverage for direct-child authorization and out-of-scope rejection, simultaneous recover_task and supervisor sweep requests, precise outcome rendering, semantic merge-conflict incident exposure, and the full derived-blocker lifecycle. Verify resolving one recovery incident clears only its matching blocker and preserves unrelated blockage provenance; avoid redundant lower-level tests already exercised by these scenarios.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
