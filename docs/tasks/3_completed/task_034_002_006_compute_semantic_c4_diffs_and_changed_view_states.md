---
id: task_034_002_006
title: Compute semantic C4 diffs and changed-view states
tier: task
status: completed
parent: feat_034_002
children: []
depends_on:
- task_034_002_002
- task_034_002_004
owners:
- swe
skills: []
parent_rev: 86ed6bbb668a679b5e3c49bcde1697df4dd3dce7
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Compute semantic C4 diffs and changed-view states

## Parent Feature

[feat_034_002](../../features/2_active/feat_034_002.md)

## Depends on

- task_034_002_002
- task_034_002_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Compare validated current/proposed model artifacts by stable semantic IDs and explicit view keys. Cover element properties, containment, relationships, and view membership while ignoring automatic layout movement and export-local numeric IDs. Enumerate every changed view, including views absent on one side; report added, removed, changed, unchanged, first-model/empty-baseline, empty proposal, removed-view, and render-error states with a textual summary and source diff reference. Require explicit reviewed rename mappings; never infer renames. Add focused cases for layout-only changes, changed membership, removals, and invalid identity. Keep this artifact/API consumable by feat_034_003 and feat_034_004 without implementing their review UI.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
