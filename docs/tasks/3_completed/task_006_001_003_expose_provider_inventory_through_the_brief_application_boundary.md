---
id: task_006_001_003
title: Expose provider inventory through the brief application boundary
tier: task
status: completed
parent: feat_006_001
children: []
depends_on:
- task_006_001_002
owners:
- swe
skills: []
parent_rev: 5d54e18d61a68714151ad90c19bcadceb4b17d38
created: '2026-10-24'
updated: '2026-10-24'
---
# Expose provider inventory through the brief application boundary

## Parent Feature

[feat_006_001](../../features/2_active/feat_006_001.md)

## Depends on

- task_006_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Wire the cached discovery inventory into the application boundary consumed by the brief UI. Define the UI-facing response so consumers receive normalized providers/models, model-scoped reasoning defaults and overrides, freshness metadata, and distinguishable loading/refresh failure state with sanitized errors. Support explicit refresh through the same boundary and add an integration-level contract test covering success, partial failure, and refresh behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
