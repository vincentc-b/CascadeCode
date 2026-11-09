---
id: task_013_003_003
title: Resume stale Task execution with fresh supervised validation
tier: task
status: completed
parent: feat_013_003
children: []
depends_on:
- task_013_003_001
owners:
- swe
skills: []
parent_rev: 302850f0b333603b26588268a1879a5052eea5c8
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Resume stale Task execution with fresh supervised validation

## Parent Feature

[feat_013_003](../../features/2_active/feat_013_003.md)

## Depends on

- task_013_003_001

## Acceptance criteria

1. A stale lease or ownerless Task execution follows its existing checkpoint and pinned provider/model/reasoning/Flex selection; route with the live Feature ID, never parent_rev or a SHA. A live or stale-but-live owner prevents duplicate kickoff.
2. Material Feature-base movement invalidates old delivery evidence. Resume the owned worktree, run fresh work-defined supervised validation, persist replacement exact-head evidence, and retry the original merge action only after rechecking current heads and gates.
3. Missing checkpoint, missing pin, dirty worktree, busy target and stale validation receive a safe repair or precise durable refusal; preserve user changes and history.
4. Prove actual owner wakeup, owned-branch mutation, supervised checks, evidence replacement and eventual merge eligibility in an isolated repository path entered from audit.

## Files likely touched

cascade/task/supervisor_recovery.py; cascade/task/checkpoint.py; cascade/task/execution.py; cascade/task_rollup.py; tests/test_task_recovery_generations_regressions.py (only as needed).

## Implementation notes

Use pinned execution inputs and existing checkpoint resume/revalidation for stale leases and ownerless turns. A material Feature-base movement must trigger fresh work-defined supervised checks and replacement exact-head delivery evidence before retrying the original action. Distinguish missing checkpoint, stale validation, dirty worktree and live/stale-but-live owner without changing user work or history. Exercise actual owner wakeup, owned branch mutation, check execution and action identity in isolated repository tests.

## Skills

_(none)_

## Test plan

Run the focused stale-input audit-entry integration scenario and relevant existing Task recovery regressions. Include a moved Feature base and a live-owner negative case.

## Out of scope

Changing pinned provider settings, bypassing validation, replaying stale evidence, destructive Git operations.
