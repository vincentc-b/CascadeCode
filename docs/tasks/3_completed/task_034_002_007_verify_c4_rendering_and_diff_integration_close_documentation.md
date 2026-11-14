---
id: task_034_002_007
title: Verify C4 rendering and diff integration, close documentation
tier: task
status: completed
parent: feat_034_002
children: []
depends_on:
- task_034_002_005
- task_034_002_006
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
# Verify C4 rendering and diff integration, close documentation

## Parent Feature

[feat_034_002](../../features/2_active/feat_034_002.md)

## Depends on

- task_034_002_005
- task_034_002_006

## Acceptance criteria

- Exercise the real pinned Structurizr image end to end from confined versioned source through validation, JSON, bound and sanitized SVG, and semantic diff.
- Prove reordered declarations, identical labels, parallel relationships, removed targets, invalid IDs/source, layout-only changes, missing/ambiguous joins, and offline/resource limits. Failed binding stays visibly noninteractive with a source diff.
- Verify the renderer consumes exactly the pinned source closure: mutation of the materialized input after closure creation must fail before rendering or produce a different validated cache key. A cache hit must not accept a result whose source provenance or required artifact bytes have changed.
- Document artifact schema, source/revision/digest provenance, failure modes, and downstream contracts for features C and D; reconcile affected DESIGN.md and architecture documentation.

## Files likely touched

C4 render/binding/diff integration, focused acceptance tests, and architecture documentation.

## Implementation notes

Run a high-signal end-to-end acceptance suite against the manifest-pinned image. The current render handoff uses `closure.digest` for its cache key but only checks that `closure.input_directory` exists before invoking the tool. Verify source bytes against the closure file hashes at the trust boundary and reject drift; preserve the same pinned repository/revision contract. Ensure cached artifacts are validated before reuse. Keep the output minimal and do not build C's review lifecycle or D's UI.

## Skills

_(none)_

## Test plan

Focused real-tool acceptance and provenance-drift regression.

## Out of scope

C's lifecycle, D's paired viewer, F's authoring workflow, and G's historical replay.
