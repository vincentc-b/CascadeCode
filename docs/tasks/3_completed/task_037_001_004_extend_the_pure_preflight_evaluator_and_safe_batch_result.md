---
id: task_037_001_004
title: Extend the pure preflight evaluator and safe batch result
tier: task
status: completed
parent: feat_037_001
children: []
depends_on:
- task_037_001_002
- task_037_001_003
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
# Extend the pure preflight evaluator and safe batch result

## Parent Feature

[feat_037_001](../../features/2_active/feat_037_001.md)

## Depends on

- task_037_001_002
- task_037_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend cascade/agent/preflight.py rather than adding another evaluator. Evaluate complete normalized role selections against supplied capability evidence with the documented stable reason/remedy vocabulary: missing/malformed configuration, unsupported adapter, discovery unavailable/empty, installation/authentication, temporary outage, absent/retired model, unsupported reasoning, provider/model Flex rejection, CLI/SDK/tool-host incompatibility, and unknown evidence. Return one safe per-role/batch contract with provenance, requested/effective Flex, actual/default reasoning, classification, eligible remedies, and inventory freshness; preserve useful existing response fields while migrating consumers. Aggregate every affected role; deterministic rejection wins the batch while transient role details remain visible. Add a table-driven failure matrix and safe serialization checks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
