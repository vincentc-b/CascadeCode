---
id: task_036_002_001
title: Route planning artifact lifecycle operations through the tracking repository
tier: task
status: completed
parent: feat_036_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 69d5d628935a4bb952aa9fe67584588f6867335d
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Route planning artifact lifecycle operations through the tracking repository

## Parent Feature

[feat_036_002](../../features/2_active/feat_036_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Route epic, feature, and task create/read/update/list operations through the repository resolved for the tracking role.

## Scope

- Persist and load planning artifacts from the tracking repository.
- Route decision history and required versioned lifecycle metadata through the same repository.
- Preserve existing colocated behavior when tracking and target resolve to the same repository.
- Consume repository-role resolution from feat_036_001; do not add migration, credential management, or general multi-repository orchestration.

## Acceptance criteria

- Epic, feature, and task create/read/update/list flows use the resolved tracking repository.
- Decision history and required versioned lifecycle metadata are stored and read there.
- Colocated operation remains backward-compatible.
- Focused integration coverage proves the routed lifecycle behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
