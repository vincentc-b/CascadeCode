---
id: task_037_001_002
title: Resolve and fingerprint complete effective role selections
tier: task
status: completed
parent: feat_037_001
children: []
depends_on:
- task_037_001_001
owners:
- swe
skills: []
parent_rev: 272318a21e2b769ed35a2db841f6b233bee7bbff
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Resolve and fingerprint complete effective role selections

## Parent Feature

[feat_037_001](../../features/2_active/feat_037_001.md)

## Depends on

- task_037_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend existing model_resolve.py, brief_stack.py, and work_backend.py paths so Epic returns all five pinned roles, Feature its two planning roles plus effective SWE, and Task SWE, with the same precedence and stamping used for actual work. Carry per-field source, owning document path/revision, provider default reasoning when applicable, reviewed/effective Flex, and stable selection fingerprint per the task_037_001_001 contract. Explicit malformed values, incomplete legacy pins, and resolver exceptions must yield structured configuration blockers with migration/default guidance rather than successful empty batches or fall-through. Add focused precedence/provenance and fingerprint invalidation tests. Do not change child lifecycle gates owned by the dependent feature.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
