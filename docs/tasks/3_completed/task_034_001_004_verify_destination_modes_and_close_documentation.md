---
id: task_034_001_004
title: Verify destination modes and close documentation
tier: task
status: completed
parent: feat_034_001
children: []
depends_on:
- task_034_001_001
- task_034_001_003
owners:
- swe
skills: []
parent_rev: 7ae7674cd7bd5124cee13de8d9764e11b3e020a9
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify destination modes and close documentation

## Parent Feature

[feat_034_001](../../features/2_active/feat_034_001.md)

## Depends on

- task_034_001_001
- task_034_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Run focused integration checks for default target mode, explicit target mode, tracking mode, invalid combinations, preservation of existing root DESIGN.md, one-home references, stable mappings after configuration changes, and fixed destinations for existing review units. Document configuration, paths, ownership rules, and known limits in the repository. Fix only gaps needed to satisfy this feature's acceptance criteria.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
