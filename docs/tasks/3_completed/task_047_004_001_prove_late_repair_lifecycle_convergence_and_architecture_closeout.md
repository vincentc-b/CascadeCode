---
id: task_047_004_001
title: Prove late repair lifecycle convergence and architecture closeout
tier: task
status: completed
parent: feat_047_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 31ba0f2f2c0b0151d65502bfc9c72a30b2f65372
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove late repair lifecycle convergence and architecture closeout

## Parent Feature

[feat_047_004](../../features/2_active/feat_047_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Acceptance requirements for this Task (the generated template's TBD fields are superseded by this sealed contract):
- Build a small temporary-repository integration matrix through normal mint, dispatch, Task final validation, queued delivery, Feature/Epic supervision, review health, watchdog admission, and review reconciliation. Use contract-accurate deterministic forge transport; do not manufacture success ledger rows or authorization events.
- Cover active Feature repair, completed-path Feature with open review, already merged review requiring a linked follow-up, and repair racing closeout. Preserve the existing Task ID and its historical validation/attempts. Assert current source and target heads on the resulting review, distinct historical acceptance, and actual parent integration.
- Share fixtures across refusal cases: moved source or target after validation, stale generation, live owner, dirty/missing checkout, changed registered owner, blocking comments, missing approval, dependency refusal, and split roots. Assert typed refusal and durable unchanged work; rerun the existing final gate before replacing a validation pair when heads move.
- Include a sibling checkout's misleading completed copy and retirement with the last terminal child absent elsewhere. Restart workers and repeat sweeps. Assert one repair action and publication per generation, no falsely active queue or incident, coherent execution/board/rollup, and discoverable terminal descendants.
- Reconcile any implementation defects exposed by the matrix within the owning Feature/Boss/Watchdog/Task/Workspace paths and focused tests, keeping scope bounded. Do not count a team wakeup or a locally merged Task as review acceptance.
- Reconcile root and affected cascade/{feature,boss,watchdog,task,workspace,epic,board,war_room}/DESIGN.md with the final diff. Maintain source-linked structure and normal/refusal/restart flows. For each affected C4 view (cascade-landscape, cascade-context, cascade-containers, cascade-supervisor-components, cascade-team-components, cascade-feature-code, cascade-boss-code, cascade-watchdog-code, cascade-workspace-code, cascade-task-code, cascade-epic-code), update model.dsl, views.dsl, workspace.contract.json only if the implemented boundary or symbols change, preserving accepted snapshots and stable IDs. Record a concrete unchanged-level reason. Validate source contract and supported real render; verify context → container → component → Code, Level up, deep-link restoration, pinned source, stale/deleted symbol and wrong-owner rejection. Record cold/warm timing and bounded artifact reuse.
Likely files: tests/test_late_repair_convergence.py or focused existing integration suite; cascade/{feature,boss,watchdog,task,workspace,review}.py modules only for defects; owning DESIGN.md and architecture source/contract only as affected.
Verification: run complete new scenario matrix and focused affected suites; run repository's bounded publication safeguards after any conflict; source-contract validation and supported Structurizr rendering/browser path. Record exact commands, revisions, failures and external gates in Feature closeout.
Out of scope: new scheduler/queue, broad audit dashboard changes, duplicate Task minting, manually edited lifecycle files, fabricated review acceptance, unrelated refactors.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
