---
id: task_024_001_005
title: Validate end-to-end backlog brief edit lifecycle
tier: task
status: completed
parent: feat_024_001
children: []
depends_on:
- task_024_001_003
- task_024_001_004
owners:
- swe
skills: []
parent_rev: 90cda45b486fd8f2c1b3900a30e6707d495bd908
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
models:
  swe: gpt-5.6-luna
---
# Validate end-to-end backlog brief edit lifecycle

## Parent Feature

[feat_024_001](../../features/2_active/feat_024_001.md)

## Depends on

- task_024_001_003
- task_024_001_004

## Acceptance criteria

- Submission fetches configured product trunk before validating source provenance, compares the submitted brief revision to that fetched brief, and renders from the fetched brief so a stale local checkout cannot overwrite a newer approved edit.
- Snapshot publication preserves the last valid snapshot if final replacement fails.
- The complete edit-review-merge-refresh lifecycle and critical negative paths pass with the compact integration suite described below.

## Files likely touched

- cascade/brief_edit_pr.py
- cascade/workspace/backlog_snapshot.py
- focused lifecycle and failure-path tests

## Implementation notes

### Known merged defects to repair before acceptance

- `cascade/brief_edit_pr.py::_submit` currently validates `source_revision` against the local resolved document before fetching remote trunk, then renders that local document into the fetched base. Move target lookup, eligibility/provenance comparison, validation, no-op detection, and rendering to the fetched trunk brief. A newer upstream target revision must return a stale/reload response without creating a branch or PR; unrelated trunk commits must remain valid.
- `cascade/workspace/backlog_snapshot.py::_publish_snapshot` currently deletes the existing snapshot before `os.replace`. Publish with an atomic/rollback-safe swap so any replacement failure leaves the prior valid snapshot readable. Clean staging/backup artifacts without touching operator checkout or active worktrees.
- Add focused regressions for both defects. Reuse the end-to-end fixtures and real temporary Git repositories rather than creating a parallel mock-heavy suite.

## Objective

Prove the complete edit-review-merge-refresh lifecycle with a compact, high-signal regression suite.

## Scope

- Exercise a real local Git repository and fake forge boundary from War Room/API submission through upstream merge and refresh.
- Edit every authoring field plus extra Markdown, then inspect that the review branch changes exactly one file at the original path and preserves ID, creation metadata, untouched content, and system-managed state.
- Merge upstream, refresh, and verify the existing board row, plan detail, assignments, and activation provenance all reference the approved revision.
- Cover both snapshot-only and stale local backlog copies with a diverged operator checkout.
- Include the critical negative paths not already adequately covered: stale source, deleted/no-longer-backlog target, invalid/unavailable assignments, explicit reasoning clear, no-op/cancel, duplicate in-flight submit, forge failure/retry, refresh failure, and late merge against live state.
- Confirm existing create-brief and human activation-gate behavior remains intact.
- Consolidate or reuse lower-level checks where the end-to-end path already provides equivalent confidence; avoid a parallel mock-heavy suite.

## Acceptance

- The lifecycle test demonstrates no local activation or approved-content overwrite before merge, then correct same-item refresh and provenance after merge.
- Negative paths create no unintended PR/MR or state mutation and preserve recoverable user input/last valid board as applicable.
- Operator checkout and active worktrees remain unchanged throughout.
- Relevant create-brief and activation regressions pass.

## Skills

_(none)_

## Test plan

Use the high-signal lifecycle path plus focused regressions for fetched-trunk stale detection and failed snapshot replacement. Avoid redundant lower-level coverage already exercised by the lifecycle.

## Out of scope

General branch reconciliation, a new sync service, automatic merge/activation, and broad snapshot subsystem redesign.
