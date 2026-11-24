---
id: task_013_003_002
title: Requeue lost validated Task deliveries through canonical merge and rollup
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
# Requeue lost validated Task deliveries through canonical merge and rollup

## Parent Feature

[feat_013_003](../../features/2_active/feat_013_003.md)

## Depends on

- task_013_003_001

## Acceptance criteria

1. From a real audit observation, detect a validated active Task whose original merge action is retryable while its entry is absent from pending-task-merges.json; reserve the current generation and invoke the existing Task supervisor adapter.
2. Recheck live Task parent, lease, approval/comment gates, exact Task and Feature heads, evidence and action ID before canonical requeue. Preserve the original action identity through one merge and terminal rollup; release the dependent Task.
3. Return durable, precise outcomes for live or stale-but-live owner, missing checkpoint, stale validation, dirty worktree and busy target. No reset, clean, force-push, replacement Task or duplicate queue.
4. Cross real queue, merge, rollup and dependency-release boundaries in an isolated repository test entered through the audit. Assert one terminal completion and unchanged user work.

## Files likely touched

cascade/task/supervisor_recovery.py; cascade/task_rollup.py; cascade/watchdog/audit_recovery.py; tests/test_task_recovery_generations_regressions.py; tests/watchdog/test_health.py (only where integration requires).

## Implementation notes

Reproduce task_038_002_002: active validated Task and retryable original merge action with absent pending-task-merges.json entry. Use the existing owner-scoped supervisor recovery, lifecycle lock, exact-head evidence checks and canonical enqueue/merge/rollup; preserve original action identity and release dependent work after one terminal completion. Handle missing checkpoint, stale validation, dirty worktree, busy target and live/stale-but-live owner with safe repair or durable precise refusal. Do not reset, clean, force-push or create a replacement Task. Add an isolated repository recovery test crossing queue, merge and rollup.

## Skills

_(none)_

## Test plan

Run the focused real audit-entry lost-queue scenario, then the relevant existing Task recovery regression module. Use deterministic provider inventory in the two health fixtures that currently fail preflight, without changing production admission.

## Out of scope

New merge algorithm, replacement Task, model diagnosis for deterministic requeue, changes to provider configuration or credentials.
