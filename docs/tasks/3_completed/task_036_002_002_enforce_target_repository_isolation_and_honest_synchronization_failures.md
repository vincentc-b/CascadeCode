---
id: task_036_002_002
title: Enforce target-repository isolation and honest synchronization failures
tier: task
status: completed
parent: feat_036_002
children: []
depends_on:
- task_036_002_001
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
# Enforce target-repository isolation and honest synchronization failures

## Parent Feature

[feat_036_002](../../features/2_active/feat_036_002.md)

## Depends on

- task_036_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Complete split-repository execution so planning preparation and synchronization affect only the tracking repository while source changes and implementation worktrees remain in the target repository.

## Scope

- Keep source mutations and implementation worktrees bound to the target repository.
- Ensure tracking storage unavailability and Git preparation/synchronization failures surface as failures, never false success.
- Preserve recoverable state for interrupted preparation or synchronization where the existing lifecycle supports retry/recovery.
- Stay within the epic non-goals: no cross-repository transactions, credential management, automatic migration, or generalized source orchestration.

## Acceptance criteria

- Split mode leaves planning-artifact changes out of the target repository.
- Source changes and implementation worktrees do not move to the tracking repository.
- Unavailable tracking storage and failed Git synchronization report actionable failure state.
- Interrupted operations can follow the supported recovery path without incorrectly marking the lifecycle complete.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
