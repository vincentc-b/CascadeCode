---
id: task_036_002_003
title: Prove split and colocated planning lifecycles end to end
tier: task
status: completed
parent: feat_036_002
children: []
depends_on:
- task_036_002_002
owners:
- swe
skills: []
parent_rev: 02eb582fb64d46b4b5181b7e0af494256eebd890
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove split and colocated planning lifecycles end to end

## Parent Feature

[feat_036_002](../../features/2_active/feat_036_002.md)

## Depends on

- task_036_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add economical, high-signal end-to-end coverage for repository-routed planning lifecycles and their critical failure modes.

## Scenarios

- Split mode advances epic/feature/task artifacts, decision history, and required lifecycle metadata in the tracking repository while the target repository remains free of those artifact changes.
- Colocated mode proves unchanged default behavior.
- Unavailable tracking storage fails without reporting success.
- Failed Git synchronization fails without reporting success.

## Acceptance criteria

- Tests exercise the public lifecycle rather than duplicating lower-level coverage.
- Assertions verify both the expected tracking-repository changes and absence of planning-artifact changes in the target repository.
- Failure scenarios assert externally visible state and error reporting.
- The suite is deterministic and uses the project’s existing repository fixtures/harness where practical.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
