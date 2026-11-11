---
id: task_030_003_001
title: Connect restored epics to the reviewed backlog edit and refresh path
tier: task
status: completed
parent: feat_030_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 4c64393c84c8ac70e80f8b7cc5854262e14ca799
created: '2026-11-01'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Connect restored epics to the reviewed backlog edit and refresh path

## Parent Feature

[feat_030_003](../../features/2_active/feat_030_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Route a restored Epic through the existing merge-request-backed backlog edit and refresh workflow so provider/model changes are reviewed before activation.

## Acceptance criteria

- A restored Epic can enter the existing backlog edit/refresh path without creating a parallel editing mechanism.
- Provider and model changes use the established MR-backed review flow.
- Refusal behavior for already-reviewed and child-work-present cases is preserved and covered at the appropriate integration boundary.
- The implementation remains limited to the restored-Epic journey required by feat_030_003.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
