---
id: task_085
title: Wire gate into dispatch_feature/dispatch_task, mint_task, and both merge paths
tier: task
status: completed
parent: feat_019
children: []
depends_on:
- task_084
owners:
- swe
skills: []
parent_rev: 2c7444bbec5e80b7b6ca1f3f9461475c0d1e4158
created: '2026-10-20'
updated: '2026-10-20'
---
# Wire gate into dispatch_feature/dispatch_task, mint_task, and both merge paths

## Parent Feature

[feat_019](../../features/2_active/feat_019.md)

## Depends on

- task_084

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Call `blocking_threads_for` from: `dispatch_feature` / `dispatch_task` (War Room human + Boss) -> `ok=false`, `reason` lists threads; `mint_task` -> REPLACE `_refuse_blocking_human_comments` (delete it, no stacked second check) and raise `FeatureToolDenied` with same text; `merge_task_branch` / `merge_feature_branch` -> refuse with `reason` (task inherits feature). Do NOT gate `mint_feature`, `activate_epic`, `confirm_epic_complete`. No `force` flag (dec_004); no new field on `DispatchResult`.

Refusal text lists each thread's `id`, `doc_id`, `section`, and `/plan/{doc_id}#plan-comments`; warnings may be appended to the same string. Reuse existing `blocked` toast if one fires; no new toast type. Completion rollup unchanged.

Tests: one API/system test per caller (dispatch, mint_task, merge task/feature) asserting refusal text includes thread id and `/plan/` link. No mocking the gate.

Note (dec_013): do not merge/close out before feat_018 lands (human-only resolve).

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
