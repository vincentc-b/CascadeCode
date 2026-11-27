---
id: task_013_005_004
title: Verify real Task, Feature, and Epic recovery through the audit entry point
tier: task
status: completed
parent: feat_013_005
children: []
depends_on:
- task_013_005_001
- task_013_005_002
owners:
- swe
skills: []
parent_rev: 99f211e18eb59cbc54f133d1a1dceceaf8c0af6c
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify real Task, Feature, and Epic recovery through the audit entry point

## Parent Feature

[feat_013_005](../../features/2_active/feat_013_005.md)

## Depends on

- task_013_005_001
- task_013_005_002

## Acceptance criteria

1. Isolated-repository audit entry fixtures drive Task lost-queue and stale-delivery, Feature owner and publication, and Epic owner and closeout incidents through their real owning capabilities to terminal outcomes exactly once.
2. Repeat task_038_002_002 and Feature ID versus parent_rev regressions through the same audit entry point.
3. Prove durable owner request, acknowledgement and result; missing capability fails closed with exact action and is automatically re-evaluated after registration or generation change.
4. Fresh approval/comment gates, dirty worktree protections, split tracking and finite retry/cooldown remain authoritative.

## Files likely touched

`tests/watchdog/test_audit_recovery.py`, `tests/feature/test_audit_recovery.py`, existing real adapter fixtures, and only the owned recovery seams needed to fix observed defects.

## Implementation notes

Use isolated repositories and existing adapter fixtures to prove default-on Task lost-queue/stale-delivery, Feature owner/publication, and Epic owner/closeout paths reach terminal outcomes exactly once. Repeat task_038_002_002 and Feature-ID-versus-parent_rev regressions through the audit entry point. Verify concrete owner wake/ack/result, fresh gates, missing-capability fail-closed evidence and automatic reevaluation. Fix defects found in the owned implementation; record commands and outcomes.

## Skills

_(none)_

## Test plan

Run the real isolated-repository audit-entry fixtures to terminal lifecycle outcomes; record exact command, final revision and observed result for each adapter.

## Out of scope

Event-only or mocked completion proof; duplicate recovery algorithms.
