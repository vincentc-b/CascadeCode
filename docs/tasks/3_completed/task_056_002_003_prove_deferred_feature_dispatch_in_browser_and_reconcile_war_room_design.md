---
id: task_056_002_003
title: Prove deferred Feature dispatch in browser and reconcile War Room design
tier: task
status: completed
parent: feat_056_002
children: []
depends_on:
- task_056_002_001
- task_056_002_002
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
# Prove deferred Feature dispatch in browser and reconcile War Room design

## Parent Feature
feat_056_002; prove the approved-but-deferred Feature journey and reconcile durable design.

## Depends on
task_056_002_001, task_056_002_002. Run against both implemented controls.

## Acceptance criteria
1. Extend the existing isolated real-Git and production HTTP fixture to reproduce Feature feat_051_006 dependent on still-active feat_051_005 using fixture identities. Approve the dependent Feature once through a real Chromium browser, refresh and restart the service, then prove a current persisted receipt and zero premature Feature/Task starts. Complete and verify the predecessor; observe exactly one canonical dependent dispatch with no second approval click. Assert event and execution-lease counts rather than button state.
2. Exercise independent sibling, integration and review blockers. Clearing the predecessor alone must not bypass them. Include late-minted approved/unapproved children and source-review mismatch as API-backed browser cases, reusing existing fixture setup instead of duplicating low-level approval unit tests.
3. Update cascade/war_room/DESIGN.md `REQ-WARROOM-READINESS-001` and `DEC-WARROOM-READINESS-001` with the current API/client action-state flow, inputs, outputs, transient state, durable receipt ownership, restart behavior, and explicit refusal/unconfirmed gates. Link `REQ-CASCADE-APPROVAL-001` in cascade/DESIGN.md without duplicating its authority rules. Keep the design free of delivery IDs, task history and claims about unrun checks.
4. Diagram impact: inspect the final diff and record outcomes for cascade-context (operator and external dependencies), cascade-containers (War Room/API, service and repository boundaries), cascade-war-room-components (Dashboard/HTTP collaboration), cascade-dashboard-code (real `featureApproveActionButton`, `initEpicPlanReadinessChrome`, new Feature control and any helper symbols), and cascade-war-room-http-code (`WarRoomRequestHandler._handle_approve_feature`, `WarRoomRequestHandler._handle_doc` if used). Update model.dsl, views.dsl, workspace.contract.json and owning design together for changed code-level declarations and relationships. Verify native declaration kinds, semantic IDs, `cascade.parent`, source links and the code-view owner. Explicitly justify any unchanged level from the diff.
5. Validate pinned model/source contract, render with supported local tooling, and exercise Context→Containers→Components→Code, Level up and deep-link restoration in the real browser. Run representative renamed/deleted-symbol and ownership-mismatch rejection checks from existing architecture tests. Measure warm navigation reuse, checking that another view does not start a renderer process and render bounds remain intact. Record measured results and limitations in the Task delivery record for Feature Team closeout, not DESIGN.md.
6. Run focused browser/API/Git and architecture checks. Review changed DESIGN.md against its parent and final diff and report design paths, resolved links, verification and remaining gaps for the Feature Team closeout.

## Files likely touched
tests/war_room/test_late_mint_feature_approval_e2e.py; related browser fixtures under tests/war_room; cascade/war_room/DESIGN.md; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/model.dsl, views.dsl, workspace.contract.json; targeted architecture tests only if behavior needs coverage.

## Implementation notes
The current end-to-end fixture has a static board source assertion; replace or supplement it with browser/API behavior. The approval service and dispatch owner remain canonical. See `cascade/approvals.py:approve_feature`, `cascade/feature/readiness.py:compute_feature_readiness`, `cascade/war_room/serialize.py:feature_readiness_to_dict`, and `cascade/watchdog/dispatch.py:dispatch_feature`. Do not claim a successful Feature start from an enabled control.

## Skills
[skills/design/SKILL.md]

## Test plan
Use /opt/conda/bin/python3.12 for scoped pytest and Playwright/Chromium; run the repository's C4 source-contract validator and supported local renderer; report actual commands, revisions, event counts and warm-navigation measurement.

## Out of scope
Live mutation of incident Features, deployment, broad architecture rewrite, new scheduler or approval ledger.
