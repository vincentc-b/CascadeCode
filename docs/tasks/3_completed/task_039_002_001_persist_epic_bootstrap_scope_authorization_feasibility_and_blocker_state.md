---
id: task_039_002_001
title: Persist epic bootstrap scope, authorization, feasibility, and blocker state
tier: task
status: completed
parent: feat_039_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 4a98db14f083ccb29fa251645b13c05a53c33428
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Persist epic bootstrap scope, authorization, feasibility, and blocker state

## Parent Feature

[feat_039_002](../../features/2_active/feat_039_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the epic-owned feature-zero bootstrap record, separate from an ordinary feature or work-item tier. Bind reviewed scope to manifest revision, dependency IDs, exact setup/check operations, paths and destinations, permitted feasibility artifacts, runtime/resource limits, cleanup, and human provenance. Model unchecked, awaiting_authorization, checking, dependency_blocked, ready; keep feasibility authorization and result separate from installation approval and dependency readiness. Persist actionable per-entry blockers and human guidance, including actor, last check, failed operation/environment/output, pinned investigation or install steps when known, expected verification, cleanup, and ping action. Preserve active epic and accepted work. Add focused integration coverage for scope/state and circular feasibility gating; no production epic_034 adapter.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
