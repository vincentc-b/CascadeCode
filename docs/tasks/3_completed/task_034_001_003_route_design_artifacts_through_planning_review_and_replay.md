---
id: task_034_001_003
title: Route design artifacts through planning, review, and replay
tier: task
status: completed
parent: feat_034_001
children: []
depends_on:
- task_034_001_002
owners:
- swe
skills: []
parent_rev: edd8c52d80c7a7018064736c831d71285f4065a6
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Route design artifacts through planning, review, and replay

## Parent Feature

[feat_034_001](../../features/2_active/feat_034_001.md)

## Depends on

- task_034_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Use the resolved architecture destination and stable mappings from task_034_001_002 for design/model reads, proposed edits, links, review references, and replay. Keep each existing review unit bound to the destination recorded when created even if cascade.toml later changes; reject silent retargeting. Integrate with existing planning/review/routing services without a new document-service UI. Add focused behavior checks at the affected service boundaries.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
