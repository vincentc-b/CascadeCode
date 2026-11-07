---
id: task_006_002_001
title: Implement validated full-stack defaults in the brief API
tier: task
status: completed
parent: feat_006_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 98cf7367830b2de330f7cd0d384905e018276082
created: '2026-10-24'
updated: '2026-10-24'
---
# Implement validated full-stack defaults in the brief API

## Parent Feature

[feat_006_002](../../features/2_active/feat_006_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Define the provider/model/reasoning fields for every epic, feature, and task role represented by the brief schema. Load choices from the discovery inventory, validate provider/model compatibility and supported reasoning overrides server-side, persist the selections through the existing brief creation path, and return them on reload/continue. Keep default reasoning implicit so provider behavior is unchanged. Add focused API/integration coverage for valid persistence and rejection of stale or unsupported selections.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
