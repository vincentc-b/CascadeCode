---
id: task_037_002_004
title: Persist complete provider blockers and recheck every process start
tier: task
status: completed
parent: feat_037_002
children: []
depends_on:
- task_037_002_001
owners:
- swe
skills: []
parent_rev: 2e851f651db32f7ec9b7c1271242a2a803da4d39
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Persist complete provider blockers and recheck every process start

## Parent Feature

[feat_037_002](../../features/2_active/feat_037_002.md)

## Depends on

- task_037_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend the existing provider blocker record with every affected role result, configuration provenance, and first/last observation while retaining one durable incident per work item across restart. Clear only after a fresh successful check of the whole blocked scope; cached readiness or an unrelated role check cannot clear it. At each Epic, Feature, and Task provider process start, refresh inventory, compare pinned execution provenance with current authorized selection, and record structured failure for missing provider/model or resolution errors before any turn. Never silently replace reviewed selections. Verify deduplication, restart, fresh-only clearing, and post-activation drift with fake inventory/process fixtures.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
