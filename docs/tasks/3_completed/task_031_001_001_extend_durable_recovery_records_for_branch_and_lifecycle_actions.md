---
id: task_031_001_001
title: Extend durable recovery records for branch and lifecycle actions
tier: task
status: completed
parent: feat_031_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 9316bb483551ef1a98c48af85fb58371bdbd5687
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Extend durable recovery records for branch and lifecycle actions

## Parent Feature

[feat_031_001](../../features/2_active/feat_031_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Define and implement the minimal extension to the existing epic_026 recovery record for branch/lifecycle failures. Persist original action identity, owning Feature or Epic Team, lifecycle state, evidence/provenance, retry/routing markers, and precise human blocker details across restart. Preserve compatibility with existing recovery records and user files/approvals.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
