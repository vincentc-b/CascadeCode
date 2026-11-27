---
id: task_034_002_005
title: Bind rendered hit targets to semantic model IDs
tier: task
status: completed
parent: feat_034_002
children: []
depends_on:
- task_034_002_001
- task_034_002_004
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
# Bind rendered hit targets to semantic model IDs

## Parent Feature

[feat_034_002](../../features/2_active/feat_034_002.md)

## Depends on

- task_034_002_001
- task_034_002_004

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement the trusted renderer-node -> exported-model-ID -> semantic-ID join proven in task_034_002_001, using only metadata from the same validated workspace export. Produce an artifact manifest or approved SVG attributes for element and relationship hit targets, and preserve/verify those bindings through SVG sanitization. Use approved local viewer assets. Never infer identity from labels, positions, source order, or transient SVG IDs. Detect ambiguous, missing, removed, or stale targets; block interactive review and expose the source diff when binding fails. Cover reordered source, identical labels in different containers, parallel relationships, removal, and sanitization with real-tool artifacts.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
