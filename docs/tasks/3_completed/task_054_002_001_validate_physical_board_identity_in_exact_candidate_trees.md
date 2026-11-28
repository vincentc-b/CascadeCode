---
id: task_054_002_001
title: Validate physical board identity in exact candidate trees
tier: task
status: completed
parent: feat_054_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: e671205bb19e833194774bf10dd325a8b86d2285
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Validate physical board identity in exact candidate trees

## Parent Feature

[feat_054_002](../../features/2_active/feat_054_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Build a read-only scan of every physical lifecycle document in the candidate checkout. Report malformed files, symlinks, duplicate IDs, tier/filename/status/column mismatches and parent-child identity with exact paths. Use board parser/store contracts and keep split-root ownership evidence explicit. Add real Git tests and reconcile Board and Teams code views.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
