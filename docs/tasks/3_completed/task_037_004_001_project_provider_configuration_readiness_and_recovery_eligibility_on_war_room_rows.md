---
id: task_037_004_001
title: Project provider configuration readiness and recovery eligibility on War Room rows
tier: task
status: completed
parent: feat_037_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 453526829bf55d5408f6a473572d602705fbf662
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Project provider configuration readiness and recovery eligibility on War Room rows

## Parent Feature

[feat_037_004](../../features/2_active/feat_037_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Use the shared selection/capability evaluator to project safe provider configuration readiness for backlog and active Epic, Feature and Task rows, distinct from lifecycle, dependency and plan readiness. Include every affected role and its provider, model, reasoning and Flex selection; safe reason, document path/revision, inventory freshness, remedies and server-computed action eligibility. Reuse one bounded cached inventory snapshot per board projection; no provider discovery per row or model turn. Make inventory refresh reproject row readiness and active dialog diagnostics without lifecycle events, queue/checkpoint mutation or new incidents; a cached success must not clear a durable blocker. Preserve command-side rechecks and the existing review/recovery paths. Add focused API/projection checks for cache use, stale/unknown state, refresh and durable blocker behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
