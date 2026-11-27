---
id: task_034_003_001
title: Persist pinned architecture review units and lineage baselines
tier: task
status: completed
parent: feat_034_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 45017d17e06b1673eeff14c65d13b30528c4153b
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Persist pinned architecture review units and lineage baselines

## Parent Feature

[feat_034_003](../../features/2_active/feat_034_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Define a durable review unit for owner/repository identity, fixed documentation destination, exact plan/design/model commits, pinned source closure and tool digest, accepted baseline (including explicit empty baseline), requirement/decision/view citations, affected work, and architecture impact or justified no-diagram-change. Resolve current architecture from the accepted pointer on the owning integration lineage, including accepted child merges without advancing trunk. Preserve proposed ancestor context separately and expose stale-baseline/rebase state. Add focused persistence and lineage checks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
