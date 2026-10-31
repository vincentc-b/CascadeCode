---
id: task_014_001_003
title: Cover cancellation lifecycle and ordering with acceptance tests
tier: task
status: completed
parent: feat_014_001
children: []
depends_on:
- task_014_001_002
owners:
- swe
skills: []
parent_rev: 72e56b3a1a440166537d3ce868251d0a647eba41
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
---
# Cover cancellation lifecycle and ordering with acceptance tests

## Parent Feature

[feat_014_001](../../features/2_active/feat_014_001.md)

## Depends on

- task_014_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add high-signal contract/integration tests at the command or API boundary for epic, feature, and task cancellation. Cover backlog and active success paths, persisted reason/metadata, whitespace-only or missing reason rejection, completed-item rejection with no mutation, and repeated cancellation idempotency (original metadata retained and downstream effects emitted at most once). Include an ordering assertion using the lightest reliable seam available to prove persistence completes before downstream effects. Avoid redundant lower-level tests already exercised by these scenarios.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
