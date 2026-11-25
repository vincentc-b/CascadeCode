---
id: task_046_001_004
title: Serve the paired review envelope and scoped immutable HTTP resources
tier: task
status: completed
parent: feat_046_001
children: []
depends_on:
- task_046_001_003
owners:
- swe
skills: []
parent_rev: e764058ea543f073d9075970e610792a3063b4c8
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Serve the paired review envelope and scoped immutable HTTP resources

## Parent Feature

[feat_046_001](../../features/2_active/feat_046_001.md)

## Depends on

- task_046_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Make production /api/doc/{id} always return the small schema_version 1 paired_review envelope for epic/feature plans, with resource_url, state/reason/message, nullable unit/digest and retry metadata; plan and Markdown comments remain usable through review errors. Serve /api/architecture/reviews/{work_id} via the authorized resolver and lazy/paginated projection. Serve sanitized semantic SVG at /api/architecture/artifacts/{scope_id}/{artifact_id} and pinned source/model/plan/design content and diffs at /api/architecture/resources/{scope_id}/{resource_id}, resolving only server-owned opaque manifests and exact repository/commit/path provenance. Verify authorization, scope membership, digest and binding on every lookup; enforce 256 KiB metadata/request, 4 MiB SVG and 1 MiB readable resource limits, correct status codes, private ETag and no-store where specified. Wire plan page to follow resource URL and expose failure/retry state. Add actual-handler tests for states, tampering, stale refs, resource readability and bounds.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
