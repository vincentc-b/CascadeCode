---
id: task_047_004_002
title: Verify GitHub CLI snapshot contract and reviewed runtime handoff
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
# Verify GitHub CLI snapshot contract and reviewed runtime handoff

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
- Keep cascade/tracking.py::merge_request_snapshot's existing GitHub commits query and final commit OID extraction. Test the actual installed gh binary's supported --json query shape through a safe local CLI invocation, then use that contract-accurate response in focused tests. Assert pinned source SHA, empty/malformed commits refusal, and changed source-head refusal before publication; retain merge SHA, mergeability, comments, descriptions, and GitLab normalization.
- Write a supported operator runbook for orchestration-code repair: identify the reviewed source revision and expected running revision, use existing drain/stop controls, update/start from the reviewed checkout through documented procedures only when separately authorized, then record observed executing revision and post-restart review-health result. Show the exact prerequisite when old running code cannot admit the repair and keep validated delivery queued. Do not imply deployment from a local Task merge.
- Exercise the handoff's local, safe evidence path with a focused test or reproducible procedure using the existing operator entry points. Mark external forge acceptance, installation and live restart as unperformed when unavailable. No dependency installation or upgrade.
- Reconcile tracking/review and operator documentation plus affected DESIGN.md interfaces. If implementation changes review or runtime wiring, inspect cascade-context, cascade-containers, cascade-supervisor-components, cascade-boss-code and other affected native Code views, then update model.dsl/views.dsl/workspace.contract.json and source-linked owning designs as needed. Preserve accepted snapshots; document exact unchanged-level reasons. Verify source-contract and supported rendering for changes.
Likely files: tests/test_tracking_find.py, tests/test_review_health.py, cascade/tracking.py only for a proven defect, README.md or docs/tracking_repositories.md and related operator instructions, affected owning DESIGN.md and C4 source only if warranted.
Verification: actual gh CLI query capability and response-shape evidence; focused tracking/review-health tests; runbook steps checked against actual CLI/operator controls; bounded publication safeguards after any conflict; architecture source-contract/render checks if changed. Record exact commands and revision.
Out of scope: gh upgrade, direct internal Python repair calls, manual event/status edits, runtime hotpatch, arbitrary package installation, claiming an external review or deployment occurred.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
