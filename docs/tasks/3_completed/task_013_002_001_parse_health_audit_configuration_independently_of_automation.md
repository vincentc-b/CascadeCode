---
id: task_013_002_001
title: Parse health-audit configuration independently of automation
tier: task
status: completed
parent: feat_013_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 20b90d6adbec9b20361ed4751aa1e8339cc8fa77
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Parse health-audit configuration independently of automation

## Parent Feature

[feat_013_002](../../features/2_active/feat_013_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add [automation.health_audit] enabled (default true) and interval (default "30m") parsing. Accept only positive integer strings with s/m/h/d units in the inclusive 1m–24h range; report invalid values explicitly while preserving unrelated delivery and legacy configuration behavior. Document independence from automation.enabled and the legacy supervisor-health sweep, including convergence through existing repair claims. Add focused configuration checks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
