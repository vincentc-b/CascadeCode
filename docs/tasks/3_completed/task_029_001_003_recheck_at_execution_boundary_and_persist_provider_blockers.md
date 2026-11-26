---
id: task_029_001_003
title: Recheck at execution boundary and persist provider blockers
tier: task
status: completed
parent: feat_029_001
children: []
depends_on:
- task_029_001_001
owners:
- swe
skills: []
parent_rev: 3049608aef9088d87a3b2c93216daf8df4ef1c6a
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Recheck at execution boundary and persist provider blockers

## Parent Feature

[feat_029_001](../../features/2_active/feat_029_001.md)

## Depends on

- task_029_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Re-run provider preflight immediately before execution. Persist a sanitized provider-blocked incident keyed to the work item so repeated attempts do not create duplicates and the blocker remains visible after restart. Represent deterministic versus transient classification without leaking secrets; do not alter unrelated work state.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
