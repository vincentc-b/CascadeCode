---
id: task_034_002_002
title: Validate versioned C4 source and semantic identities
tier: task
status: completed
parent: feat_034_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: a4967f542037b78de330e56fe87bf78ccc91b240
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Validate versioned C4 source and semantic identities

## Parent Feature

[feat_034_002](../../features/2_active/feat_034_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the repo-owned Structurizr workspace and fragment contract under the architecture destination from feat_034_001. Define fragment ownership and stable workspace-unique, nonempty semantic IDs for each reviewable element and relationship, with explicit unique view keys. Treat exporter numeric IDs as export-local. Require a reviewed explicit rename mapping for continuity. Give derived relationships and dynamic occurrences deterministic source/view/occurrence identities or a visible unsupported error. Validate duplicate/missing IDs and keys before rendering. Keep source and fixture changes versioned; prove reorder, duplicate labels, parallel relationships, and invalid-ID cases with focused tests. No remote or executable DSL extensions.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
