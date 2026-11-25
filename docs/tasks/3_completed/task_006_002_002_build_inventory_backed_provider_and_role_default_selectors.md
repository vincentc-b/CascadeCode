---
id: task_006_002_002
title: Build inventory-backed provider and role default selectors
tier: task
status: completed
parent: feat_006_002
children: []
depends_on:
- task_006_002_001
owners:
- swe
skills: []
parent_rev: 40173969c17ff69ea29b07b4ba1aab8b4f3e9137
created: '2026-10-24'
updated: '2026-10-24'
---
# Build inventory-backed provider and role default selectors

## Parent Feature

[feat_006_002](../../features/2_active/feat_006_002.md)

## Depends on

- task_006_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Replace free-text model inputs in brief creation with provider and per-role model selectors backed by the discovery inventory. Show reasoning choices only when configurable, include the default option, and clear or revalidate incompatible model and reasoning values when upstream selections change. Implement explicit loading, no-usable-provider, and recoverable-error states; disable submission while selections are invalid or inventory is empty.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
