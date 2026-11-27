---
id: task_056_002_002
title: Add Feature approval control to plan page with reviewed context
tier: task
status: completed
parent: feat_056_002
children: []
depends_on:
- task_056_002_001
owners:
- swe
skills: []
parent_rev: 3a1b93ea9bc500a6b7e31322c7af5b50b6adb7ce
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Add Feature approval control to plan page with reviewed context

## Parent Feature
feat_056_002; consume its approved Feature authorization and plan-readiness contract.

## Depends on
task_056_002_001. Use the shared approval action semantics and visible review context established there.

## Acceptance criteria
1. The Feature plan page shows a distinct `Approve feature` control when canonical Feature approval is pending. It presents the exact current reviewed tuple/revision and submits that displayed `review_context` to `/api/approve_feature`; absent/stale context disables approval with a concrete corrective path. Keep Epic `Approve plan` behavior and tactical Feature planning separate.
2. Pending disables immediately and survives intervening readiness GETs; saved approval reports execution `waiting` with typed prerequisite codes and affected work IDs until canonical readiness advances. Explicit HTTP refusal stays by the control across later GETs; timeout/disconnect is unconfirmed and reconciles via canonical doc/board evidence before a safe retry.
3. A delayed POST or older GET cannot erase newer approval evidence. Refresh/restart reconstructs current approval from the server, not transient browser state. Keyboard focus, role=status/alert and accessible labels announce outcomes.
4. Add API-backed browser tests for Feature and Epic controls, reviewed-scope change, provider/architecture/software refusal, delayed transport, repeated input, stale reads and screen-reader-visible state. Existing Epic approval browser scenarios remain green.
5. Diagram impact: verify cascade-context and cascade-containers still describe the same boundaries; cascade-war-room-components retains the Dashboard and HTTP components. Update cascade-dashboard-code for `initEpicPlanReadinessChrome`, the new Feature plan approval entry point and `EpicPlanReadinessUi.applyReadinessToPlanBar` if changed; cascade-war-room-http-code for `WarRoomRequestHandler._handle_approve_feature` only if changed. Reconcile semantic IDs, `cascade.parent`, source paths/symbols and native element kinds in model.dsl, views.dsl and workspace.contract.json. Owning design: cascade/war_room/DESIGN.md.

## Files likely touched
cascade/war_room/static/plan_viewer.js; cascade/war_room/static/epic_plan_readiness_ui.js; cascade/war_room/static/feature_readiness_ui.js; plan-page HTML/view rendering only as needed; focused tests/war_room browser fixtures.

## Implementation notes
`GET /api/doc/{id}` already carries `paired_review.approval_context` for Epic/Feature. A Feature readiness field may need to be serialized for the plan page from the same canonical service used by board GET. Preserve the existing bounded POST deadline; do not infer authorization from button state.

## Skills
[]

## Test plan
Run scoped browser/API tests against the HTTP service, then the existing Epic plan approval integration script. Assert exact submitted context, one POST per gesture and visible refusal/reconciliation.

## Out of scope
Changing `approve_feature`, defining a second approval receipt, scheduling work, and broad plan-viewer redesign.
