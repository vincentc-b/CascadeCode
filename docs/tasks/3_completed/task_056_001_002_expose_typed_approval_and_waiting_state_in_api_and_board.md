---
id: task_056_001_002
title: Expose typed approval and waiting state in API and board
tier: task
status: completed
parent: feat_056_001
children: []
depends_on:
- task_056_001_001
owners:
- swe
skills: []
parent_rev: dfdc6b6b957f76a62a8fc2e74fc0cbec0908d5c7
created: '2026-11-27'
updated: '2026-11-27'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose typed approval and waiting state in API and board

## Parent Feature

[feat_056_001](../../features/2_active/feat_056_001_separate_durable_feature_approval_from_execution_dependency_gates.md)

## Depends on

- task_056_001_001

## Acceptance criteria

1. Preserve `/api/approve_feature` legacy success/refusal fields and board readiness fields. Add a typed approval result and canonical approval state, explanation and affected work IDs. A saved timestamp plus current matching receipt is approved even when immediate dispatch refuses; return HTTP success with waiting evidence and no false execution claim.
2. Project approval eligibility independently of execution readiness on the server, using the approval-only predecessor policy from task 1. Board reads remain read only; missing or stale receipt and changed scope/declaration cannot appear approved. Keep sibling, required integration, review, provider, software and parent blockers visible in the execution projection.
3. Keep the current HTTP operator route's identity and review-context boundary. Verify stale displayed context, changed scope, corrective-plan, provider and architecture/comment refusals precede approval writes. Typed refusal identifies its reason and affected work IDs.
4. Cover Epic bulk and late-child behavior through existing paths: included approved children stay approved, a newly minted child is unapproved until explicit human approval, and repeat approval cannot silently accept a stale reviewed scope.
5. Reconcile `cascade/war_room/DESIGN.md`, `cascade/feature/DESIGN.md` and the package approval interface for the implemented response/projection. Update significant `cascade-war-room-http-code`, `cascade-dashboard-code`, `cascade-feature-code` and `cascade-approval-code` nodes/source-contract entries as needed, with real source paths and declaration kinds. Record concrete no-change reasons for context, containers, components and Watchdog Code if untouched.

## Files likely touched

`cascade/approvals.py`, `cascade/feature/readiness.py`, `cascade/war_room/server.py`, `cascade/war_room/serialize.py`, `cascade/war_room/static/war_room.js` only if presentation requires it, `cascade/war_room/DESIGN.md`, `cascade/feature/DESIGN.md`, `cascade/DESIGN.md`, architecture model/contract/view files, `tests/test_approvals.py`, `tests/war_room/test_board_feature_readiness.py`, `tests/war_room/test_late_mint_feature_approval_e2e.py`.

## Implementation notes

Use existing approval and dispatch reconciliation. Do not infer execution from `approved_at` alone. Keep old response keys for clients. The UI can show a work wait while approval remains current. Preserve the current request authentication behavior rather than introducing an unrelated auth system.

## Skills

None beyond SWE role defaults.

## Test plan

Run focused production HTTP and board-projection tests using isolated real-Git repositories. Test a known incomplete predecessor, later completion, missing/cancelled/illegal predecessor, stale review context, stale scope/declaration, provider and architecture refusals, and a saved approval with dispatch refusal. Validate native Code/source-contract coverage and locally render changed views; inspect context-to-Code navigation, Level up, deep-link restoration and pinned source opening.

## Out of scope

New scheduler or receipt store, relaxed Epic sign-off/minting rules, dependency installation, deployment, unrelated dashboard redesign.
