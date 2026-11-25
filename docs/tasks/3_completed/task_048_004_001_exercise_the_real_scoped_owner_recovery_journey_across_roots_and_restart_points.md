---
id: task_048_004_001
title: Exercise the real scoped owner recovery journey across roots and restart points
tier: task
status: completed
parent: feat_048_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 92a0e7274bde4963097b90e4aa974dc45ae7be21
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Exercise the real scoped owner recovery journey across roots and restart points

## Parent Feature

[feat_048_004](../../features/2_active/feat_048_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope
Extend `tests/test_late_repair_convergence.py` and `tests/test_review_recovery_journey.py` as one shared acceptance harness. Inject a genuine recoverable failure, let a scripted provider call production scoped owner tools, then run real Task tests/commit/delivery, bounded review validation, leased publication, remote observation and fresh Watchdog postcheck. Use temporary product/tracking repositories, a bare remote, real validator processes and durable stores. No direct post-admission lifecycle edits, raw success setter, fake green validation, fake publication or fake final verification. Keep old publication regression.

## Acceptance
- Cover normal and split roots; timeout plus exhausted decision across worker restart, approved policy correction, and an unavailable policy-owner wait. Include interruption before claim, during checks, after commit, immediately after push and before completion receipt; recover through production reconciliation without duplicate effects.
- Bind exact original incident, action/generation, claim, profile, immutable tested SHA, remote target/lease, reviewed/integrated/installed/loaded revision and fresh postcheck. Assert provider/process/worker/Task/review/message/publication effects independently, including repeated sweeps and concurrent callers. Preserve pending claims, attempts and diagnostics.
- Cover late completed-parent repair, descendant ownership, pending delivery and product acceptance remaining distinct from a passing review. Confirm provider and forge scripts only replace external transport.
- Architecture: trace `cascade-landscape`/`cascade-context` and `cascade-containers` boundaries; reconcile `cascade-supervisor-components`, `cascade-team-components`, `cascade-task-code`, `cascade-agent-code`, `cascade-watchdog-code`, `cascade-teams-code`, affected tier and workspace Code views against actual changed source. Owning designs are root, `cascade/DESIGN.md`, `cascade/{task,agent,watchdog,workspace,feature,epic}/DESIGN.md`. If production symbols/interfaces change, update source-linked design, `model.dsl`, `views.dsl`, `workspace.contract.json` together; otherwise record source-backed no-change. Include normal/failure restart, persistence, authority and isolation limits; validate source contract/render and representative context → container → component → Code, Level up, deep links and pinned source. Never rewrite accepted snapshots.
- Record focused test commands, revisions, design paths reviewed, actual architecture checks and unresolved gaps in task closeout.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
