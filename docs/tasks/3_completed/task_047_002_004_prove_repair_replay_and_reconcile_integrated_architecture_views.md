---
id: task_047_002_004
title: Prove repair replay and reconcile integrated architecture views
tier: task
status: completed
parent: feat_047_002
children: []
depends_on:
- task_047_002_003
owners:
- swe
skills: []
parent_rev: 1483db9ba964514a2150912d36e1dfc662bbb8e2
created: '2026-11-24'
updated: '2026-11-24'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove repair replay and reconcile integrated architecture views

## Parent Feature

[feat_047_002](../../features/2_active/feat_047_002_admit_late_repair_generations_without_losing_accepted_review_history.md); use pinned parent_rev and its diagram-impact inventory.

## Depends on

- task_047_002_003

## Acceptance criteria

- Exercise the assembled production boundaries for active parent, completed/open review and merged/accepted review repair. Use normal scoped admission, mint, watchdog authorization, Task final validation/delivery, review publication/reconciliation and Boss closeout. Prove one original Task identity, immutable old acceptance, exact current follow-up heads and deferred retirement until descendant/current-obligation proof. No hand-edited ledger, fabricated event or manually constructed success result.
- Fault-inject prepared action, event append, active document move/commit, validation replacement, review-record save, acceptance callback and acknowledgement. Repeated sweeps and restart converge on the same action/generation and one publication. A changed owner, stale generation, live lease, moved source/target, dirty or missing checkout, unresolved human comment, missing approval/dependency and terminal Epic produce typed refusal/next action while preserving work. Cover split product/tracking roots and a misleading sibling historical copy where relevant to feat_047_001's owner contract.
- Prove admission racing closeout in both orders and an old merged callback after a newer obligation. Current child, review, integration and retirement postchecks must agree; no queued delivery or incident is falsely resolved. Limit checks to this Feature's core transaction/regression scope; feat_047_003 owns parent/audit routing and feat_047_004 owns full cross-feature end-to-end/deployment proof.
- Review cascade/feature/DESIGN.md, cascade/task/DESIGN.md, cascade/boss/DESIGN.md, cascade/watchdog/DESIGN.md and cascade/DESIGN.md against final diff. Remove stale/speculative statements and history attribution; ensure stable IDs have one owner, parent/child interfaces agree, source-linked implementation and normal/refusal/restart diagrams cover action, validation, review and closeout.
- Reconcile `cascade-feature-code`, `cascade-task-code`, `cascade-boss-code` and affected `cascade-watchdog-code` nodes with real sourcePath/sourceSymbol, actual declaration kind and workspace.contract.json. Record concrete no-change reasons for landscape/context/containers and unchanged component edges; update component views where collaborators changed. Verify source-contract validation, supported pinned Structurizr render, checkout-relative links, context→container→component→Code Explore, Level up, deep-link restore, representative pinned source and warm artifact reuse. Do not rewrite accepted snapshots.
- Record the exact test revision, results, measured local rendering/navigation, design paths reviewed/updated, unresolved gates and diagram-impact results in the Feature work closeout. Local tests and review integration do not assert runtime deployment.

## Files likely touched

Focused integration tests under tests/feature/, tests/task/, tests/boss/, tests/watchdog/ and tests/lifecycle/; cascade/{feature,task,boss,watchdog}/DESIGN.md, cascade/DESIGN.md; architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5/{model.dsl,views.dsl,workspace.contract.json}; production files only for defects exposed by these tests.

## Implementation notes

Use current APIs from predecessor Tasks and feat_047_001 owner/survival proof. Keep tests high-signal and bounded; avoid duplicating unit assertions already covered by production-boundary scenarios. The architecture model must describe implementation that exists, not proposed symbols. Coordinate Watchdog Code ownership with feat_047_003 when later routing work changes those nodes. Keep publication revision-pinned and preserve accepted lineage.

## Skills

_(none; default SWE and design role playbooks apply)_

## Test plan

Run focused Feature/Task/Boss/Watchdog and review integration cases for normal, refusal, race and restart behavior; source-contract validator and supported render/navigation checks; git diff --check. Report exact passing/failing tests and baseline limitations. Verify source and design links plus representative Code node preview. Full repository suite is not the default gate.

## Out of scope

General audit dashboard, deterministic parent/audit incident routing of feat_047_003, complete operator deployment proof of feat_047_004, new scheduler/queue, blanket completed-Feature reopening and unrelated architecture inventory.
