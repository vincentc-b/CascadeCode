---
id: task_045_002_001
title: Persist feature attention ledger and reconcile mint provenance
tier: task
status: completed
parent: feat_045_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 9d5aeae17b30380dd0c4c8b74b33739188a129a9
created: '2026-11-13'
updated: '2026-11-13'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Persist feature attention ledger and reconcile mint provenance

## Parent Feature

[feat_045_002](../../features/2_active/feat_045_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the versioned workspace-shared attention ledger at the canonical tracking trunk, with cross-process lock, atomic persistence, strict validation, monotonic revision and explicit unavailable state. Serialize first-run baseline with feature mint; record FeatureMinted provenance, reconcile missing canonical IDs at startup, and preserve seen state across replay, status/path/revision changes. Baseline only open backlog/ready-to-plan features under active non-cancelling Epics as initially New; record all historical IDs. Cover split roots, interrupted bootstrap, corrupt/missing initialized state, mint crash gap, concurrent mint, and durable restart. Follow the pinned feature plan; do not alter lifecycle approval semantics or install packages.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
