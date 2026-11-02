---
id: task_029_001_001
title: Implement shared provider capability preflight
tier: task
status: completed
parent: feat_029_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 7655dacdbad99c0704808980be6ae00d8c025c83
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Implement shared provider capability preflight

## Parent Feature

[feat_029_001](../../features/2_active/feat_029_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Create the reusable provider/model/tier capability check used across lifecycle boundaries. Return structured outcomes that distinguish deterministic unsupported configuration from transient provider/setup failure, while avoiding unrelated side effects. Define the minimal result/error contract needed by callers.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
