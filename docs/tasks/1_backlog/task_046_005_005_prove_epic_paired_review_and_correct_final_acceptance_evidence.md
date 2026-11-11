---
id: task_046_005_005
title: Prove epic paired review and correct final acceptance evidence
tier: task
status: backlog
parent: feat_046_005
children: []
depends_on:
- task_046_005_004
owners:
- swe
skills: []
parent_rev: 15184f3e0a743a762877ec893e166179364c2792
created: '2026-11-11'
updated: '2026-11-11'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Prove epic paired review and correct final acceptance evidence

## Parent Feature

[feat_046_005](../../features/2_active/feat_046_005.md)

## Depends on

- task_046_005_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

# Scope
Extend the existing real Structurizr/native Chromium planning journey in tests/war_room/test_architecture_planning_browser_journey.py. Use the supported epic planning/publication path to create a meaningful epic proposed model with container/component and relationship changes. Open /plan/epic_001 in the running War Room, assert nonempty current/proposed SVG independently checked against pinned model revisions, visible plan adjacency and exact provenance (review unit, code/doc refs, tuple, renderer settings). Retain a screenshot and runtime manifest for the epic route. Update docs/task_artifacts/task_046_005_004_final_acceptance.md so A10 and the integrated verdict reflect actual results. Rerun the relevant real renderer/browser journey from a clean render cache; no fabricated payloads, endpoint mocks, or skips. Preserve completed proof tracks. Coordinate renderer timeout evidence with the Epic Architect's amendment decision; do not change the approved 90-second contract without amendment.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
