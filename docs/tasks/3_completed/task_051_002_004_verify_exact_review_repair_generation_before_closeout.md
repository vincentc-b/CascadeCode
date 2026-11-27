---
id: task_051_002_004
title: Verify exact review repair generation before closeout
tier: task
status: completed
parent: feat_051_002
children: []
depends_on:
- task_051_002_003
owners:
- swe
skills: []
parent_rev: f834c5c379eaa970b2d29e938d582ab00d8b5858
created: '2026-11-26'
updated: '2026-11-26'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Verify exact review repair generation before closeout

## Parent Feature

[feat_051_002](../../features/2_active/feat_051_002_admit_durable_scoped_repairs_for_open_feature_reviews.md)

## Depends on

- task_051_002_003

## Acceptance criteria

- `repair_event_authorizes` accepts only the current admitted action, exact owner/active-path introduction, review identity, source/target route and committed blob. Stale event, changed owner, head or generation refuses.
- Independent Watchdog postcheck re-reads canonical action, corrected source/head, current required-check policy and results, accepted original review generation and intended Epic target integration before setting verified or permitting retirement. Task execution, queue acknowledgement, Feature reactivation, publication and green checks for an old head remain verification pending.
- Missing, stale or unavailable policy/check/forge evidence yields a typed prerequisite and retains the owner, branch, review and incident receipt. Claim and finite incident/provider/validation budgets survive restart and duplicate requests; only the exact current generation can be marked verified.
- Preserve existing accepted/merged-review follow-up and completed-parent Task-mismatch postcheck behavior. Use fresh external observation outside lifecycle critical sections and current owner/claim fences around mutation.
- Reconcile `cascade/watchdog/DESIGN.md`, affected Feature/Epic/package designs and `cascade-watchdog-code`/affected `cascade-feature-code` nodes in model.dsl, views.dsl and workspace.contract.json. Document normal and stale/failure/restart paths, source-linked symbols/kinds and persistent state; verify context → container → component → Code, Level up, deep link and pinned source.

## Files likely touched

`cascade/feature/repair.py`, `cascade/watchdog/loop.py`, `cascade/watchdog/incident_postcheck.py`, review/owner evidence readers if their contract changes; owning designs and architecture source closure.

## Implementation notes

Consume authoritative current required-check evidence when available. The subsequent review-health Feature owns GitHub/GitLab normalization; unknown policy or checks must not be treated as green. Keep verification separate from admission and execution.

## Skills

_(none)_

## Test plan

Extend Watchdog authorization and parent lifecycle postcheck suites, plus focused Feature repair, Epic parent, kickoff, mint and publication safeguard tests. Use temporary Git and scripted forge/check observations for current, stale, missing and changed evidence; fault-inject restart before verification. Run source-contract validation, pinned render and actual navigation/source-opening checks; record measured warm artifact reuse and remaining gaps.

## Out of scope

Cross-forge check normalization, War Room UI, force merge, CI bypass and deployment.
