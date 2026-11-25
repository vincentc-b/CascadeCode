---
id: task_039_003_002
title: Expose human bootstrap review, per-entry approval, and ping actions
tier: task
status: completed
parent: feat_039_003
children: []
depends_on:
- task_039_003_001
owners:
- swe
skills: []
parent_rev: 59ef39ddb241d5bfc925123b4e7e5908c5024f63
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose human bootstrap review, per-entry approval, and ping actions

## Parent Feature

[feat_039_003](../../features/2_active/feat_039_003.md)

## Depends on

- task_039_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add human-only actions through existing War Room/API authorization and lifecycle paths for narrow bootstrap-scope review, explicit installation/upgrade approval, and Ping team after completion/resume. Accept the exact displayed dependency binding and reject stale submissions; persist independent approval with human provenance for each batch entry, preserving unchanged entries when one changes. Keep scope review, plan approval, installation approval, and ping distinct. Direct API requests must use Cascade's operation gate, including implicit pulls; read-only discovery/validation needs no installation prompt. Return current projection and actionable refusal reasons. Verify stale binding, selective invalidation, independent batch records, plan/ping not granting authority, and duplicate ping/restart behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
