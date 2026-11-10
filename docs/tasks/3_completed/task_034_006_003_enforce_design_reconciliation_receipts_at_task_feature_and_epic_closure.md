---
id: task_034_006_003
title: Enforce design reconciliation receipts at Task, Feature, and Epic closure
tier: task
status: completed
parent: feat_034_006
children: []
depends_on:
- task_034_006_002
owners:
- swe
skills: []
parent_rev: c04f2743f9f9a01f82a7a5aeedc0d54b02f4e6a8
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Enforce design reconciliation receipts at Task, Feature, and Epic closure

## Parent Feature

[feat_034_006](../../features/2_active/feat_034_006.md)

## Depends on

- task_034_006_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

At each closure tier inspect the implemented change against affected directory designs, ancestor summaries, and C4 views. Record the inspected implementation and design/model revisions, affected design and ancestor paths, and either the accepted update or a concise justified no-change result. Block material mismatches and permit closure after a reviewed update; reject split-repository acceptance_pending as receipt evidence. Integrate with existing lifecycle gates and authorized stage/review/merge path. Acceptance: code-only no-diagram-change closes with a valid receipt, mismatch blocks then clears after accepted update, and pending split promotion holds closure.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
