---
id: task_013_003_005
title: Converge restart, parent recovery and simultaneous audits
tier: task
status: completed
parent: feat_013_003
children: []
depends_on:
- task_013_003_004
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
# Converge restart, parent recovery and simultaneous audits

## Parent Feature

[feat_013_003](../../features/2_active/feat_013_003.md)

## Depends on

- task_013_003_004

## Acceptance criteria

1. Crash/restart, manual Feature recovery and simultaneous audits converge on the same original action and one worker, validation, queue, merge and terminal rollup. Pending versus accepted exact-token claims survive an interrupted handoff, including attempt bound 1; only the current matching token may finish.
2. Negative outcomes honor cooldown and finite attempts; a changed authoritative generation, including capability arrival, re-evaluates correctly without erasing prior attempts. A healthy pass remains silent and deterministic repairs use zero auditor model turns.
3. From the real audit entry, demonstrate lost queue through exactly one canonical merge/rollup and dependent release; stale input through fresh supervised validation and replacement evidence; owner conflict route, acknowledgement/result and matching blocker clearance. Preserve split tracking authority and user history.
4. Correct the two health-test provider-preflight fixtures with deterministic inventory. Do not weaken production preflight. Report the integrated evidence to Feature 005, which owns the all-tier default-on release gate.

## Files likely touched

cascade/watchdog/audit_recovery.py; cascade/watchdog/reservations.py; cascade/task/supervisor_recovery.py; tests/test_task_recovery_generations_regressions.py; tests/watchdog/test_health.py (only as needed).

## Implementation notes

Make crash/restart, manual parent recovery and simultaneous audit attempts converge on one original action, worker, validation, queue, merge and terminal rollup using shared bounded generation/cooldown semantics. Interrupted claims and negative outcomes retry only on eligible authoritative generations; capability changes re-evaluate visible missing adapters. Extend tests/test_task_recovery_generations_regressions.py and tests/watchdog/test_health.py with isolated repository scenarios that cross actual owner route, wakeup, acknowledgement, supervised checks, replacement evidence, blocker reconciliation and merge/rollup. Assert one terminal completion and unchanged user history.

## Skills

_(none)_

## Test plan

Run the focused isolated repository audit-entry recovery and concurrency scenarios, then the relevant existing recovery modules. Assert original action identity, exact token accounting and one terminal completion.

## Out of scope

Feature 005 settings/UI/default-on release, provider changes, dependency installs, duplicate model or queue paths.
