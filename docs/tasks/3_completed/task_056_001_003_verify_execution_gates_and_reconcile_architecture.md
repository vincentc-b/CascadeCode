---
id: task_056_001_003
title: Verify execution gates and reconcile architecture
tier: task
status: completed
parent: feat_056_001
children: []
depends_on:
- task_056_001_001
- task_056_001_002
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
# Verify execution gates and reconcile architecture

## Parent Feature

[feat_056_001](../../features/2_active/feat_056_001_separate_durable_feature_approval_from_execution_dependency_gates.md)

## Depends on

- task_056_001_001
- task_056_001_002

## Acceptance criteria

1. Use isolated real-Git integration tests to approve a Feature while a legal predecessor is incomplete; confirm the receipt is current, Feature remains in backlog, no Feature planning or Task execution starts, and later canonical Watchdog/Boss ticks admit exactly one execution only after all gates pass.
2. Prove predecessor completion alone does not bypass required intended-target delivery evidence. Cover sibling activity, review threads, provider/software blocks, unknown/cancelled/regressed dependencies, stale approval receipt and changed reviewed context. Preserve supported stacked dispatch semantics.
3. Verify restart after timestamp-before-receipt interruption remains non-dispatchable and an explicit approval retry repairs evidence. Exercise duplicate and concurrent approvals and late-child Epic behavior with no duplicate Feature launch or unauthorized bulk approval.
4. Reconcile the final code diff with `DESIGN.md`, `cascade/DESIGN.md`, `cascade/feature/DESIGN.md`, `cascade/watchdog/DESIGN.md`, `cascade/war_room/DESIGN.md` and affected child interfaces. Update durable requirements, decisions, source links, approval sequence, receipt state, and failure/restart flow; keep delivery IDs and chronology in the work record.
5. Reconcile `cascade-landscape`, `cascade-context`, `cascade-containers`, `cascade-supervisor-components`, `cascade-team-components`, `cascade-war-room-components`, `cascade-approval-code`, `cascade-feature-code`, `cascade-dashboard-code`, `cascade-war-room-http-code`, `cascade-watchdog-code` and `cascade-boss-code` against actual changes. Update native Code elements/relationships and semantic IDs for significant changed symbols, preserve source-contract ownership, and give concrete no-change reasons for unaffected levels.
6. Validate architecture source contract and supported local render. Inspect Context → Containers → Components → Code, Level up, deep-link restoration and pinned source opening for representative nodes. Trace a normal approval-and-dispatch scenario and a refusal/restart scenario against code. Record tested revision, design paths, results and gaps in the work closeout.

## Files likely touched

`tests/test_approval_dispatch_integration.py`, `tests/test_approvals.py`, `tests/test_planning_action_dependencies.py`, `tests/war_room/test_late_mint_feature_approval_e2e.py`, focused Watchdog/Feature tests only as needed, affected `DESIGN.md` files, `architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}`, implementation only for integration defects revealed by tests.

## Implementation notes

Tasks 1 and 2 define the policy and response. This task supplies cross-boundary proof and final documentation reconciliation. Use current dispatch paths; do not add a second scheduler. Preserve revision-pinned architecture publication. Keep verification bounded to affected paths and repair only concrete failures.

## Skills

None beyond SWE role defaults.

## Test plan

Run the focused approval, dependency, late-child, Feature dispatch and delivery-gate suites. Execute source-contract validation and local Structurizr render when supported. Use a browser or equivalent integration check for drill-down, Level up, deep-link restore and source opening; report any environment limitation explicitly. Do not treat a successful render alone as navigation proof.

## Out of scope

New approval system, blanket strict-dependency relaxation, installation, deployment, full-repository test suite without a concrete risk.
