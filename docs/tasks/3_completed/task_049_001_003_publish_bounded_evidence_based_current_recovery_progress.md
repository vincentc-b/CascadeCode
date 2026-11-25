---
id: task_049_001_003
title: Publish bounded evidence-based current recovery progress
tier: task
status: completed
parent: feat_049_001
children: []
depends_on:
- task_049_001_001
- task_049_001_002
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
# Publish bounded evidence-based current recovery progress

## Parent Feature

[feat_049_001](../../features/2_active/feat_049_001_project_evidence_based_recovery_progress.md)

## Depends on

- task_049_001_001
- task_049_001_002

## Acceptance criteria

- Derive one versioned safe progress entry from matching action + generation + attempt/claim, live tokens, Watchdog stages and fresh same-generation postcheck. Cover requested/queued, acknowledged, investigating, executing, waiting/blocked with concrete prerequisite/owner, retryable failed, exhausted, verification pending, verified complete and stale/unavailable. Enqueue, `mutation_ready`, successful attempt and publication do not prove execution or resolution. Preserve unknown legacy time/provenance and sanitize targets/reasons.
- Publish product-root `.cascade/recovery_progress/v1/work/<sha256(work-id)>/current.json` pointers to immutable revision manifests and bounded pages. Manifest embeds exact work/product/tracking identity, schema/revision, runtime identity, observed/expiry times, completeness and lag. Owning graph and affected work aliases share entry identity/revision. Writer-only disposable stdlib SQLite index tracks current entries, imported receipts, dirty identities and fair cursors; existing action/incident stores remain authoritative.
- Keep concurrent entries in deterministic order: unresolved blockers, other unresolved, verified complete, then newest material occurrence and stable identity. Preserve continuation; a stale entry retains last supported blocker priority. Update only affected work pages; never rebuild the full health-audit epoch per event or load the monolithic ledger once per receipt in a batch.
- Best-effort after-lock fast path publishes one affected batch within 250 ms, leaving explicit lag on fence/disk failure. `watchdog_tick` drains early outside `process_lock` before slow work; worker startup schedules the same drain. Bound each pass to 100 receipts/owners or one second with persistent fair continuation. Reconcile source-committed receipts after missed notifications/restart; legacy import reports incomplete until finished. No independent service/timer, paid turn or recovery ledger.
- Tests cover every state, conflicting/mismatched source, concurrent actions, fresh/expired/dead owner, missed notification, restart, immutable alias revisions, fair backlog, publication lag and source-cost measurements. Reconcile `cascade/war_room/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/task/DESIGN.md` and parent interfaces, adding source-linked normal/failure Mermaid flows. Update real `cascade-dashboard-code`, `cascade-watchdog-code`, `cascade-task-code` and component ancestors; sync model.dsl/views.dsl/workspace.contract.json and verify native source kinds. See feature plan's shared API and diagram inventory.

## Files likely touched

- A publisher under `cascade/watchdog/` or the existing supervisor-owned projection boundary, with its writer-only SQLite index and immutable product-root pages.
- Existing Task action, Watchdog stage/postcheck and Workspace worker evidence readers used by the publisher.
- `cascade/war_room/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/task/DESIGN.md`, relevant parent designs, and synchronized architecture model, views and source contract.

## Implementation notes

Consume committed receipts and exact live tokens from Tasks 1 and 2. Keep the writer index disposable and source actions/incident records authoritative. Drain the pending work before slow watchdog dispatch, outside `process_lock`.

## Skills

_(none)_

## Test plan

Run focused producer integration tests with committed source receipts, matched and mismatched live tokens, same-generation postcheck, concurrent blockers and a lost notification. Exercise restart replay, fair bounded drain, alias revision identity, legacy incomplete coverage and source-cost/publication-lag measurements. Validate source contract, local render and normal/failure Code-view links.

## Out of scope

Public GET, board rendering and room UI belong to Task 4. Do not introduce a new scheduler, repair authority, transcript ledger or model turn.
