---
id: task_038_001_003
title: Build safe dependency-status projection from authoritative evaluation
tier: task
status: completed
parent: feat_038_001
children: []
depends_on:
- task_038_001_002
owners:
- swe
skills: []
parent_rev: 855508b1a1a61e62bb0531bb8252408dc830a4b1
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Build safe dependency-status projection from authoritative evaluation

## Parent Feature

[feat_038_001](../../features/2_active/feat_038_001.md)

## Depends on

- task_038_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

For every declared dependency, return work ID, tier/status/column when known, outcome satisfied, dependency_unmet, or dependency_status_unavailable, safe completion evidence, and stable unavailable reason (dependency_not_found for an absent ID on a valid board; stable source-failure reason otherwise). Include observation time and opaque authoritative revision/fingerprint with clear snapshot semantics. Represent every declared ID; an empty list is satisfied. Do not derive evidence from document read access or transcript text, and exclude bodies, comments, prompts, raw paths, exception text, and secrets. Add focused projection tests for completed but unreadable, incomplete, cancelled/mismatch, missing, source-unavailable, and empty cases.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
