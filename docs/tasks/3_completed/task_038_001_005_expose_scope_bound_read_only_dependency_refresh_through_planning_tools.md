---
id: task_038_001_005
title: Expose scope-bound read-only dependency refresh through planning tools
tier: task
status: completed
parent: feat_038_001
children: []
depends_on:
- task_038_001_003
owners:
- swe
skills: []
parent_rev: 855508b1a1a61e62bb0531bb8252408dc830a4b1
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Expose scope-bound read-only dependency refresh through planning tools

## Parent Feature

[feat_038_001](../../features/2_active/feat_038_001.md)

## Depends on

- task_038_001_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Register a read-only refresh for epic and feature planning through the existing tool registry, custom-tool path, and MCP transport. Derive allowed dependency IDs from the caller's current owning spec at call time; accept no arbitrary IDs or paths. Return only the safe projection, retain existing sandbox allowlists and scoped document authorization, and make cross-team content reads report content_access_denied independently. Test both transports and tiers for scope isolation, refresh after authoritative board changes, and continued denial of arbitrary enumeration/content reads.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
