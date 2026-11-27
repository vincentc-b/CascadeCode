---
id: task_037_003_003
title: Persist scoped runtime Flex waiver and selection provenance
tier: task
status: completed
parent: feat_037_003
children: []
depends_on:
- task_037_003_001
owners:
- swe
skills: []
parent_rev: 8bb76119d1cabb729e4ff6e9c7a855a074319204
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Persist scoped runtime Flex waiver and selection provenance

## Parent Feature

[feat_037_003](../../features/2_active/feat_037_003.md)

## Depends on

- task_037_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the contract's runtime service-tier override for the validated role scope and normal stamped descendants. Preserve reviewed plan text, plan hashes, approval/sign-off revisions, provider/model/reasoning pins, existing siblings and independent child overrides. Carry waiver provenance into minted/executed selections. Invalidate on relevant configuration or revision changes and prevent unrelated changes from broadening scope. Persist only the specified non-secret authorization and freshness evidence.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
