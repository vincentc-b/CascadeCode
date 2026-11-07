---
id: task_006_001_002
title: Build resilient provider inventory discovery and cache
tier: task
status: completed
parent: feat_006_001
children: []
depends_on:
- task_006_001_001
owners:
- swe
skills: []
parent_rev: 5d54e18d61a68714151ad90c19bcadceb4b17d38
created: '2026-10-24'
updated: '2026-10-24'
---
# Build resilient provider inventory discovery and cache

## Parent Feature

[feat_006_001](../../features/2_active/feat_006_001.md)

## Depends on

- task_006_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Aggregate provider adapter results into one authoritative inventory, isolating partial provider failures so healthy providers remain available. Add a small bounded cache for successful discovery with an explicit freshness policy, expiry behavior, and forced refresh path. Return sanitized failure state without credentials or secret-bearing provider errors. Include high-signal tests for filtering unavailable providers, partial failure, cache hits, expiry, and explicit refresh.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
