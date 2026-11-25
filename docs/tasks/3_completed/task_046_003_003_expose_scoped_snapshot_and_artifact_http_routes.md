---
id: task_046_003_003
title: Expose scoped snapshot and artifact HTTP routes
tier: task
status: completed
parent: feat_046_003
children: []
depends_on:
- task_046_003_002
owners:
- swe
skills: []
parent_rev: 88793bda1f8a5edde89ffc70211195637aeabef4
created: '2026-11-11'
updated: '2026-11-11'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose scoped snapshot and artifact HTTP routes

## Parent Feature

[feat_046_003](../../features/2_active/feat_046_003.md)

## Depends on

- task_046_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add /api/architecture/contexts, POST /api/architecture/snapshots, GET /api/architecture/snapshots/{id}, scoped artifact/resource reads and a cheap HEAD-change status route. Return paginated bounded metadata with view/level inventory, semantic target and drill data, initial view, code/document provenance, optional accepted lineage and only a proven associated proposal review link. Revalidate known context and immutable descriptor on each read; use opaque identifiers, sanitized annotated SVG, private ETag revalidation, no-store mutable status and explicit 400/404/409/202/429 plus ordinary lifecycle JSON states. Expose only pinned readable source/model/document resources. HTTP tests cover forged/out-of-scope IDs, invalid semantic deep-link targets, distinct split refs, pending/failed render, caching and no review-unit creation.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
