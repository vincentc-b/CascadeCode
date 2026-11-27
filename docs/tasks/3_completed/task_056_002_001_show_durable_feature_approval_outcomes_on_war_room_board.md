---
id: task_056_002_001
title: Show durable Feature approval outcomes on War Room board
tier: task
status: completed
parent: feat_056_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: abbc6287ec54dce524049a8642c6cb9ae449ea6e
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Show durable Feature approval outcomes on War Room board

## Parent Feature

[feat_056_002](../../features/2_active/feat_056_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Parent Feature
feat_056_002; consume the completed feat_056_001 approval API and readiness projection.

## Depends on
None.

## Acceptance criteria
1. Board Feature approval uses the exact review context/revision visibly presented to the operator. Fetch a scoped review envelope on demand if needed; show the tuple before enabling submission. Missing or changed context yields an actionable row-local refusal, with no approval of unseen scope.
2. Build one per-work-item action state across row replacement: idle, pending, saved-awaiting-prerequisite, explicit refusal, and unconfirmed transport. A click disables immediately; repeated clicks, rerenders and older polls cannot duplicate POST or clear newer evidence. Reconcile timeout/disconnect against canonical GET before enabling retry.
3. Render the response's approval_result, approval_state, approval_explanation, affected_work_ids, execution_state and canonical readiness reasons/IDs. A current receipt remains visible through predecessor, sibling, integration and review waits; explicit refusal stays on that row across polls with the existing corrective action or retry. Keyboard focus and live-region text announce the state.
4. Preserve the server's bounded approval write deadline and canonical authorization. Do not add a browser ledger, new scheduler or provider capability discovery to board GET.
5. Add an API-backed browser test for late-minted unapproved and already-approved children, delayed/repeated clicks, out-of-order board polls, explicit refusal with work IDs, unknown transport and keyboard/screen-reader feedback.
6. Diagram impact: cascade-context and cascade-containers keep the same operator/War Room/service boundaries; verify unchanged. cascade-war-room-components must continue to show Dashboard and HTTP owners. In cascade-dashboard-code, reconcile `featureApproveActionButton`, `appendFeatureReadinessUi` and any new action helper against real source; in cascade-war-room-http-code, keep `WarRoomRequestHandler._handle_approve_feature` linked if its interface changes. Update model.dsl, views.dsl and workspace.contract.json only for changed source symbols/relationships, with semantic IDs, declaration kinds and source links validated. Owning design: cascade/war_room/DESIGN.md.

## Files likely touched
cascade/war_room/static/war_room.js; cascade/war_room/static/feature_readiness_ui.js; scoped tests under tests/war_room; cascade/war_room/serialize.py only if the existing read projection lacks a required presentation field.

## Implementation notes
Use `/api/approve_feature` and the authoritative `readiness.approval` object. The current `featureApproveActionButton` sends only `{id}` and has no durable per-row action state. Keep the new state small and keyed by Feature ID; canonical board/doc evidence wins over transient messages. The approval route is `WarRoomRequestHandler._handle_approve_feature` in cascade/war_room/server.py.

## Skills
[]

## Test plan
Run focused War Room browser/API tests, including an actual Chromium journey against the local HTTP fixture. Assert POST count and visible DOM/ARIA state from responses.

## Out of scope
Approval authority, dependency gate changes, Feature scheduler, new notification product, and edits to live incident Features.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
