---
id: task_026_004_003
title: Add dirty-trunk epic-close regression coverage
tier: task
status: completed
parent: feat_026_004
children: []
depends_on:
- task_026_004_002
owners:
- swe
skills: []
parent_rev: 8afe236aac71e1d61a745c95ea791e4f5cef4658
created: '2026-10-27'
updated: '2026-10-30'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Add dirty-trunk epic-close regression coverage

## Parent Feature

[feat_026_004](../../features/2_active/feat_026_004.md)

## Depends on

- task_026_004_002

## Acceptance criteria

- A system/integration scenario begins with unrelated tracked edits, staged/index changes, and untracked files in the operator product-trunk checkout.
- The scenario completes epic close through the normal review and persisted-action path.
- After close, tracked and untracked file bytes, index entries, HEAD, and current branch match the pre-close snapshot.
- The isolated checkout is cleaned up without removing or altering operator-owned state.

## Files likely touched

The existing epic-close integration/system test suite and only the minimal supporting fixtures needed for the scenario.

## Implementation notes

Prefer one high-signal regression over redundant unit cases. Compare explicit pre/post snapshots of file bytes and index/checkout identity.

## Skills

_(none)_

## Test plan

Run the focused dirty-trunk regression and the existing epic-close integration suite that exercises the same orchestration path.

## Out of scope

Exhaustive filesystem permutations, performance testing, or broad workspace-framework refactoring.
