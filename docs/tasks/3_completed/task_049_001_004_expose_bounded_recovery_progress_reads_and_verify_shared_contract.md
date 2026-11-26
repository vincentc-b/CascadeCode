---
id: task_049_001_004
title: Expose bounded recovery progress reads and verify shared contract
tier: task
status: completed
parent: feat_049_001
children: []
depends_on:
- task_049_001_003
owners:
- swe
skills: []
parent_rev: 9c97b16f8c3d6853c7a1903cbaddd71c1fcd83e0
created: '2026-11-25'
updated: '2026-11-25'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose bounded recovery progress reads and verify shared contract

## Parent Feature

[feat_049_001](../../features/2_active/feat_049_001_project_evidence_based_recovery_progress.md)

## Depends on

- task_049_001_003

## Acceptance criteria

- Implement `GET /api/recovery/progress?work_id=<id>&cursor=<opaque>` with the feature plan's v1 envelope, default 50/max 100 entries, exact work identity, revision-bound continuation and typed pending/409 restart behavior. Reuse the published reader for board rows. Preserve existing `recovery_incident` primary summary while adding version/revision, entry identity, freshness, count and continuation; board and room must select the same published action/revision.
- GET opens only direct no-follow regular-file work pointer, immutable manifest and requested pages with aggregate 100-entry, 1 MiB source and 256 KiB response ceilings, including multiple board work IDs. No raw action/incident scan, writer SQLite open/init, checkpoint, Git/provider/process probe, write or model work. Wrong-root, corrupt, missing, stale and incomplete evidence is explicit rather than healthy empty.
- Freeze receipt ID, entry ID, field names, route/error/cursor shape and sanitized target/provenance with feat_049_002 before delivery. Supply API fixtures that dependent transcript/UI work can consume.
- Verify that every material source transition is receipt-backed and replayable, including completed-task reconciliation and validated retry rearming; close any source gap before treating projection coverage as complete.
- High-signal API and browser/loopback tests exercise all states, queued but idle, live investigation vs live execution, waiting on checks/publication, dead/expired owner, retry/exhaustion, generation mismatch, concurrent blockers, repeated refresh, held executor, source-commit notification loss, restart, split product/tracking roots, stale cursor, read budgets and no read side effects. Reproduce the epic_044 timeline fixture at this boundary without claiming transcript/UI acceptance that belongs to dependent features.
- Reconcile final diff against `DESIGN.md`, `cascade/DESIGN.md`, `cascade/war_room/DESIGN.md`, `cascade/task/DESIGN.md`, `cascade/watchdog/DESIGN.md` and `cascade/workspace/DESIGN.md`; record updates/no-change reasons and gaps in closeout. Validate model.dsl/views.dsl/workspace.contract.json source contract and local render. Verify context → containers → components → native Code, Level up, deep-link restore and pinned source opening for progress nodes; check renamed/deleted symbols, component ownership, warm artifact reuse and render-process bounds. Trace normal and dead-owner/restart flows; report measured timing. No delivery IDs or history in DESIGN.md.

## Files likely touched

- War Room route, bounded published-progress reader, board projection and API fixtures under `cascade/war_room/` and `tests/war_room/`.
- `DESIGN.md`, `cascade/DESIGN.md`, `cascade/war_room/DESIGN.md`, `cascade/task/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/workspace/DESIGN.md`, and synchronized architecture model, views and source contract.

## Implementation notes

Reuse Task 3's published immutable pages for both room and board. Coordinate the exact receipt, entry, cursor and error contract with feat_049_002 before delivery. Record concrete design-review paths, checks and gaps in the task closeout rather than in DESIGN.md.

## Skills

_(none)_

## Test plan

Run focused loopback API and browser tests over real published pages for the listed states and failure paths. Include completed-task reconciliation and retry rearming after a missed notification, then restart the publisher and verify the new state from committed receipts. Assert no GET-side writes, probes or raw ledger access; enforce aggregate row, source-byte and response-byte ceilings and revision-bound cursors. Validate model/source contract, local render, context-to-Code and back navigation, deep links, pinned source opening, warm artifact reuse and render bounds. Record measured results.

## Out of scope

Transcript event rendering and dependent room UI behavior belong to feat_049_002. Do not infer repair authority or verified completion from a read projection.
