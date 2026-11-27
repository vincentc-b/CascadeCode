---
id: task_046_004_001
title: Resolve explicit C4 documentation links from pinned evidence
tier: task
status: completed
parent: feat_046_004
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 4eb2d4546c5ad324f01524d73aee69c4d642a677
created: '2026-11-11'
updated: '2026-11-11'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Resolve explicit C4 documentation links from pinned evidence

## Parent Feature

[feat_046_004](../../features/2_active/feat_046_004.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Build a shared, bounded context resolver for view, element, and relationship selections. Use stable requirement/decision IDs, explicit citations, design ownership/mappings, and reviewed associations; support many-to-many links. Keep explicit target coverage separate from broader owner/directory context. Return source-section references, repository/revision provenance, and visible missing/stale states. Never infer coverage from labels or prose. Add focused mapping and provenance tests. Preserve the selected review or branch snapshot revisions, including split-repository associations.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
