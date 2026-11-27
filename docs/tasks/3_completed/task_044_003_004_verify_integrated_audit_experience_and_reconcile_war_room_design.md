---
id: task_044_003_004
title: Verify integrated audit experience and reconcile War Room design
tier: task
status: completed
parent: feat_044_003
children: []
depends_on:
- task_044_003_001
- task_044_003_002
- task_044_003_003
owners:
- swe
skills: []
parent_rev: 667cfc75045946a1779a0e52f6d4601be9508401
created: '2026-11-14'
updated: '2026-11-14'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify integrated audit experience and reconcile War Room design

## Parent Feature

[feat_044_003](../../features/2_active/feat_044_003_present_actionable_health_coverage_and_retained_recovery_history.md)

## Depends on

task_044_003_001, task_044_003_002, task_044_003_003.

## Acceptance criteria

- Focused producer/API/UI integration evidence covers multiple old failures, a timed-out first candidate, a later verified blocker, repeated generations, malformed legacy remediation, and completed work with outstanding publication.
- Exercise worker restart, manual audit, split product/tracking roots, concurrent GET and multiple browser refreshes; assert GET has no lifecycle/Git/provider probes or runtime mutation and refreshes do not repeat repair side effects.
- Run existing representative 10,000-attempt GET and bounded producer benchmarks; record environment, p95 and actual byte/work counts in an inspectable work record. Keep any unmet target explicit.
- Reconcile War Room DESIGN.md and affected interface-owner design text with stable local IDs, accurate links and verification paths; omit delivery history and task/feature identifiers from design prose.
- Smoke-check a locally running War Room and preserve evidence. Normal post-deployment live acceptance remains an explicit Feature closeout gate.

## Files likely touched

- tests/war_room/
- tests/watchdog/
- cascade/war_room/DESIGN.md
- cascade/DESIGN.md if shared interface changes

## Implementation notes

Prefer one integrated fixture that exercises the real producer and loopback route, plus the existing Node UI harness. Reuse upstream tests and benchmarks rather than duplicate low-level cases. The Feature Lead will verify the deployed War Room after approved integration; do not claim that local smoke is deployment evidence.

## Skills

None beyond SWE role defaults.

## Test plan

Run focused pytest and Node harnesses, tests/war_room/benchmark_audit_get.py and tests/watchdog/benchmark_audit_producer.py. Inspect design cross-references and report any limitation in the work record.

## Out of scope

Raw ledger cleanup, broad suite, source migration, false resolution and a pre-deployment claim of live acceptance.
