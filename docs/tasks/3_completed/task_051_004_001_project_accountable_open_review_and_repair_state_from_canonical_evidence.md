---
id: task_051_004_001
title: Project accountable open-review and repair state from canonical evidence
tier: task
status: completed
parent: feat_051_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: b01c579afe1d42c595c173b7b9297d03efa5b704
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Project accountable open-review and repair state from canonical evidence

## Parent Feature

[feat_051_004](../../features/2_active/feat_051_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope and acceptance
Extend the existing Feature review projection and War Room board/open-review/room read surfaces to show the original PR URL and number, accountable Feature and Epic, implementation versus delivery status, current CI/feedback evidence and freshness, repair request/generation, admitted/acknowledged/executing/verified state, and a typed next prerequisite. Preserve visibly awaiting-review state for completed/open Features and legacy generation-zero records. Reuse the canonical review registry, Feature repair action and safe recovery-progress publication; no parallel status store. Missing or stale forge/check policy remains explicit unknown. GET, board refresh, browser polling and plan opening must not query forge authority, mutate records, enqueue work or start a provider. Bound response work and bytes using existing projection patterns.

## Verification
Extend tests/war_room/test_open_reviews_api.py and relevant board/progress API tests with current, pending, unavailable, completed-open and split product/tracking cases. Assert read-only calls do not change lifecycle evidence or invoke forge/provider. Run focused suites.

## Design handoff
Own cascade/war_room/DESIGN.md read-projection contract and source-linked normal/unknown flow; touch cascade/recovery_progress/DESIGN.md only if its published contract changes. Reconcile parent/consumer links and architecture model.dsl, views.dsl, workspace.contract.json for affected cascade-war-room-components and cascade-dashboard-code nodes, with real paths/symbols, declaration kinds and metadata. Inventory cascade-landscape/context/containers with concrete change or no-change reasons. Validate source contract and pinned render; record actual navigation, Level up, deep-link and pinned-source evidence plus read-only failure trace in closeout. Preserve accepted snapshots.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
