---
id: task_046_001_001
title: Make C4 rendering bounded, durable, and recoverable
tier: task
status: completed
parent: feat_046_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 7359e7b3250871e031987a0a33517af674838cfe
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Make C4 rendering bounded, durable, and recoverable

## Parent Feature

[feat_046_001](../../features/2_active/feat_046_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the project-scoped render scheduler and durable operation ledger using the existing C4ArtifactRenderer and review store. Deduplicate by exact closure/image/adapter/settings identity; default to one active render and 32 admitted pending jobs, preserving the 90-second renderer timeout. Persist intent, leases, attempts, failure reasons and verified artifact identity; reconcile interrupted work at startup and permit one automatic recovery attempt. GET handlers must never render. Repair tests/workspace/test_c4_render.py's nested final-validation fixture inventory while keeping strict closure checks. Add focused cache/recovery tests, including interruption and retry.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
