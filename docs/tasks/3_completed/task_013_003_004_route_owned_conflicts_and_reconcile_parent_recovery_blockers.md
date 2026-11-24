---
id: task_013_003_004
title: Route owned conflicts and reconcile parent recovery blockers
tier: task
status: completed
parent: feat_013_003
children: []
depends_on:
- task_013_003_002
- task_013_003_003
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
# Route owned conflicts and reconcile parent recovery blockers

## Parent Feature

[feat_013_003](../../features/2_active/feat_013_003.md)

## Depends on

- task_013_003_002
- task_013_003_003

## Acceptance criteria

1. Resolve team-owned conflict authority from the actual work ID and durable review identity; send a concrete owner request, wake an idle/completed owner and durably record acknowledgement and result for that request. Keep semantic ambiguity with the owning team/human.
2. At the canonical safe merge boundary, clear only blockers derived from the matching child and original action after successful repair; preserve unrelated sibling/manual blockers, approval/comment gates and imported 25794f1f/6e32c7f4 protections.
3. Prove owner route, wakeup, owned-branch conflict resolution, durable request/ack/result and scoped blocker reconciliation in an isolated repository recovery scenario.

## Files likely touched

cascade/watchdog/audit_recovery.py; cascade/watchdog/blockage.py; cascade/task/action_recovery.py; cascade/task_rollup.py; tests/test_task_recovery_generations_regressions.py (only as needed).

## Implementation notes

Route existing team-owned conflict recovery to the actual owning work ID; wake an idle or completed owner and durably persist acknowledgement/result. Keep ambiguous semantic conflicts with owning team or human. Before resuming, clear only matching derived parent blockers, preserving unrelated sibling and manual blockers. Preserve approvals, comments, original retryable action, provider and credentials. Add an isolated repository test crossing owner route, conflict result and blocker reconciliation.

## Skills

_(none)_

## Test plan

Run the focused real owner-route and blocker-reconciliation scenario plus relevant existing conflict recovery tests.

## Out of scope

Automatic semantic conflict choice, broad blocker clearing, new reconciliation path or approval/comment bypass.
