---
id: task_039_001_001
title: Persist revisioned dependency manifests and environment contracts
tier: task
status: completed
parent: feat_039_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: d270bb5ccd67c03e801ac57ca7a2faf1a4ee947f
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Persist revisioned dependency manifests and environment contracts

## Parent Feature

[feat_039_001](../../features/2_active/feat_039_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement an epic-owned dependency manifest in the tracking repository, distinct from work-item depends_on. Define stable dependency IDs, required entry fields, revision/snapshot semantics, target and actual environment identity, and an explicit validated `none required` manifest. Expose read/write and validation contracts for slice B. Existing epics start with no manifest and must supply one at their next guarded planning action; do not fabricate one or disturb accepted work. Include focused integration/API coverage for absent, empty, and revised manifests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
