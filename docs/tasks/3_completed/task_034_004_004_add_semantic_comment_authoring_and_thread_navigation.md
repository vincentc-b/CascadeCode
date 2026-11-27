---
id: task_034_004_004
title: Add semantic comment authoring and thread navigation
tier: task
status: completed
parent: feat_034_004
children: []
depends_on:
- task_034_004_002
- task_034_004_003
owners:
- swe
skills: []
parent_rev: 02a8e1b5f5223cc7da3d0d4f2eb6dc09f63354ff
created: '2026-11-09'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Add semantic comment authoring and thread navigation

## Parent Feature

[feat_034_004](../../features/2_active/feat_034_004.md)

## Depends on

- task_034_004_002
- task_034_004_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Connect the paired diagram viewer to the existing review-comment authoring and reading paths. A reviewer can open an anchored thread from a requirement, view, element, or relationship on either pinned side; show its semantic target, repository/revision, original source and diff links, open/resolved and blocking state, and visible outdated reason. Navigate from each thread to its paired view and target when current; retain original links and an explicit outdated state when removed or renamed. Use task 003's immutable typed anchors and authorized resolution path, and task 002's shared view/selection/history state. Do not infer targets from labels, exporter IDs, heading slugs, or SVG order. Cover create/read/navigation for all four anchor kinds plus outdated and cross-repository cases in focused browser or API scenarios. No freehand annotation or new comment-store workflow.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
