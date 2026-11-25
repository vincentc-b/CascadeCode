---
id: task_013_002_003
title: Execute fair bounded audit passes with finite I/O
tier: task
status: completed
parent: feat_013_002
children: []
depends_on:
- task_013_002_002
owners:
- swe
skills: []
parent_rev: e59aa03b361ef5b40e3507c8f9c71ec02c0a9fad
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Execute fair bounded audit passes with finite I/O

## Parent Feature

[feat_013_002](../../features/2_active/feat_013_002.md)

## Depends on

- task_013_002_002

## Acceptance criteria

1. Select and observe at most 100 work items under one 60-second observer/coordinator deadline. Bound candidate discovery, document-revision Git lookup, direct-child reads, and every other actual subprocess or network operation by the remaining deadline and operator cancellation.
2. Preserve fair, exact continuation when the selected page cannot be fully observed within one ordinary pass budget. Persist a successfully bounded partial page with a cursor that resumes at the first unobserved candidate, including across tiers. Do not classify routine budget exhaustion as a failure; do not skip unseen IDs.
3. Treat missing or unresolved candidate evidence as unavailable evidence with forward cursor progress. A malformed or missing work item must not repeatedly block later healthy candidates.
4. Keep the cross-process workspace claim held until all observer work exits. A timed-out or cancelled observer must not remain alive after the claim is released. Terminate descendant Git process groups and bound cleanup even when a child inherits output pipes.
5. Preserve the feature branch's canonical product-workspace claim/receipt, startup cleanup, lane-owned cancellation, and source-update/crash shutdown behavior while integrating this Task. Healthy observation remains read-only; true failures/timeouts leave durable actionable evidence and bounded retry without a completed receipt.
6. Commit the deliverable before invoking Cascade swe_run_tests on a clean Task tree. The final scoped validation must report final_validation green; shell-only tests do not satisfy the Task merge gate.

## Files likely touched

- `cascade/board/gitutil.py`
- `cascade/watchdog/audit.py`
- `cascade/watchdog/audit_lane.py`
- `cascade/workspace/worker.py`
- `tests/board/test_gitutil.py`
- `tests/watchdog/test_audit.py`
- `tests/watchdog/test_audit_lane.py`
- `tests/workspace/test_worker_startup_recovery.py`

## Implementation notes

Use the existing canonical audit selector and opaque cursor, not a parallel identity or ledger. Selection, observation, and coordination share one deadline. Long repair/model work stays in existing supervised workers outside the scheduler and global locks. Preserve the current Task branch work and merge the latest feature base through the normal Task workflow.

## Skills

_(none)_

## Test plan

Run focused tests for blocked document-revision Git lookup, candidate discovery timeout, inherited-pipe subprocess cancellation, FIFO or other blocked observer cancellation with real workspace claim contention, unresolved Task evidence progress, and deterministic multi-pass midpage continuation reaching later tiers without duplicate or skipped IDs. Retain worker tests for blocked-startup operator stop, source-update EXIT_UPDATE, and crash classification. Run the Task's scoped Cascade swe_run_tests after the final commit and confirm final_validation is green.

## Out of scope

Production default-on activation remains gated to feat_013_005.
