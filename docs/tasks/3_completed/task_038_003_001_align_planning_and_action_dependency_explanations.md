---
id: task_038_003_001
title: Align planning and action dependency explanations
tier: task
status: completed
parent: feat_038_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: dc7bd73f904777a080fed384a7197c74839daac9
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Align planning and action dependency explanations

## Parent Feature

[feat_038_003](../../features/2_active/feat_038_003.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Use the shared dependency projection and action results from feat_038_001/002 in planning context, plan readiness, and feature minting guidance. Preserve machine-readable outcomes/reasons separately from human explanations. Keep unrelated readiness and review blockers distinct. Represent content_access_denied, dependency_unmet, and dependency_status_unavailable separately; never infer unmet from a denied spec read. Ensure the next normal action reflects a completed dependency and rejects stale-success at the action boundary. Add focused API-level coverage against existing fixtures for these operator paths.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
