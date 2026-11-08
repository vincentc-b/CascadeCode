---
id: task_013_001_001
title: Define typed audit identities and pure observation contract
tier: task
status: completed
parent: feat_013_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 8e081a838858cdd2b582ef3e0c5c6285613be8cf
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Define typed audit identities and pure observation contract

## Parent Feature

[feat_013_001](../../features/2_active/feat_013_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Outcome
Introduce typed Task/Feature/Epic audit observation and incident identity structures with explicit work ID, tier, document revision, Git head, branch, generation, and evidence fields. Resolve tracking and product repositories through canonical repository resolution. Classify healthy, expected wait, proven incident, and unavailable evidence without mutation.

## Acceptance
- Typed validation rejects a Feature ID supplied as parent_rev or any interchange of work ID, revision, branch, head, and generation.
- Task, Feature, and Epic projections expose the authoritative inputs required by feature criteria 1 and 7; approval, comment, dependency, and live-owner waits remain gates.
- Pure projection never invokes mutating sweeps, provider/forge work, queue events, writes, or notifications.
- Reuse existing supervisor, execution, board, and recovery projections; keep the current direct-report sweep as a separate mutation path.

## Validation
Use focused projection cases across all tiers and split tracking/product repositories. No model or forge access.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
