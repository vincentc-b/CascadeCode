---
id: task_046_001_002
title: Publish exact architecture reviews through normal epic and feature tools
tier: task
status: completed
parent: feat_046_001
children: []
depends_on:
- task_046_001_001
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
# Publish exact architecture reviews through normal epic and feature tools

## Parent Feature

[feat_046_001](../../features/2_active/feat_046_001.md)

## Depends on

- task_046_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Register authenticated publish_architecture_review in normal epic and feature tool registries/MCP schemas and planning instructions. Derive actor, owner and ProjectContext from invocation. Validate committed plan/design/model refs, source inventory, accepted lineage pointer/generation and ownership; route ancestor-owned changes to their owner. Persist idempotent publication intent before rendering, return pending operation ID, and publish validated unit/diff/discovery only after bounded render completes. Handle explicit no_diagram_change with rationale separately from missing publication. Recheck plan revision and baseline before current-unit publication; superseded work never becomes current. Preserve exact render identity in reviewed tuple and pending approval hold. Cover normal tool calls, stale writes, partial acceptance and restart discovery.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
