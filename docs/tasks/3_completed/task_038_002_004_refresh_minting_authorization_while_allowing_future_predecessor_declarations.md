---
id: task_038_002_004
title: Refresh minting authorization while allowing future predecessor declarations
tier: task
status: completed
parent: feat_038_002
children: []
depends_on:
- task_038_002_001
owners:
- swe
skills: []
parent_rev: 1cfec10b6c847fa75f0a1ce75c93352a25a33cb0
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Refresh minting authorization while allowing future predecessor declarations

## Parent Feature

[feat_038_002](../../features/2_active/feat_038_002.md)

## Depends on

- task_038_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Refresh the owning item's prerequisites at feature minting guidance and mutation boundaries so stale turn/request snapshots cannot authorize a child artifact. Preserve tier and existence validation for declared predecessor features, but allow a new backlog child to declare existing incomplete predecessors for future sequencing. On unavailable or unmet owning prerequisites, refuse before child creation; keep ordinary no-dependency minting compatible.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
