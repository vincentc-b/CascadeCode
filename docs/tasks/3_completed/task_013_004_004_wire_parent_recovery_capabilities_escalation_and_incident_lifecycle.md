---
id: task_013_004_004
title: Wire parent recovery capabilities, escalation, and incident lifecycle
tier: task
status: completed
parent: feat_013_004
children: []
depends_on:
- task_013_004_001
- task_013_004_002
- task_013_004_003
owners:
- swe
skills: []
parent_rev: 2b8e5f1452993d96fc263be155cc99b87c2d0035
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Wire parent recovery capabilities, escalation, and incident lifecycle

## Parent Feature

[feat_013_004](../../features/2_active/feat_013_004.md)

## Depends on

- task_013_004_001
- task_013_004_002
- task_013_004_003

## Acceptance criteria

1. Register Feature/Epic owner-wake, child-dispatch, publication and rollup operations with allowed failure classes, concrete owner authority, evidence, finite retry, lock/recheck protocol and durable result path. Startup and per-incident probes reject an event-only or unreachable operation.
2. Route Task incidents to Feature, Feature incidents to Epic, and Epic/system gaps to Boss/human with responsible work ID, evidence, original action identity and exact resume action. Do not infer a human approval.
3. Persist request, acknowledgement and result for the admitted generation. Dedupe unchanged incident/notification; reassess changed generations and expired claims; retain pending or failed publication/cleanup/rollup beyond seven days.
4. Clear only the matching derived blocker after the exact result reconciles; preserve unrelated sibling and manual blockers. Missing capability or unsafe/unknown effect remains an owned actionable incident.

## Files likely touched

`cascade/watchdog/capabilities.py`, `cascade/watchdog/audit_recovery.py`, `cascade/watchdog/incidents.py`, `cascade/watchdog/reservations.py`, `cascade/watchdog/blockage.py`; focused capability/incident tests.

## Implementation notes

Use `project_incident`, `probe_capability`, `reserve_after_recheck` and `record_result` with existing ledgers. Reserve only after locked fresh generation/gate check; run slow owner work outside broad locks. Retain exact action/claim identity across restart and concurrent manual recovery. Escalation records a precise missing operation and waits for availability rather than claiming success.

## Skills

_(none)_

## Test plan

Exercise registered startup/per-incident probes, request/ack/result persistence, restart after acknowledgement, stale generation, unchanged dedupe, expired claim, sibling blocker preservation and concurrent manual recovery. Use real owner adapters where effect is asserted.

## Out of scope

A new review queue, incident database, War Room UI and default-on release.
