---
id: task_037_001_003
title: Normalize capability evidence and portable inventory freshness
tier: task
status: completed
parent: feat_037_001
children: []
depends_on:
- task_037_001_001
owners:
- swe
skills: []
parent_rev: 272318a21e2b769ed35a2db841f6b233bee7bbff
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Normalize capability evidence and portable inventory freshness

## Parent Feature

[feat_037_001](../../features/2_active/feat_037_001.md)

## Depends on

- task_037_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend existing discovery/inventory types and adapter normalization to distinguish unsupported adapter, empty/unavailable discovery, missing installation, missing authentication, temporary provider outage, and incompatible CLI/SDK or required tool-host capability. Keep environmental probes outside the pure evaluator; no model turns, credential persistence, or raw-error serialization. Represent unknown capability evidence as unknown, never verified support. Make inventory age/freshness safe across restart (do not interpret monotonic timestamps as wall-clock dates) while preserving bounded cache behavior. Add focused discovery/inventory tests for safe evidence and restart-safe age.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
