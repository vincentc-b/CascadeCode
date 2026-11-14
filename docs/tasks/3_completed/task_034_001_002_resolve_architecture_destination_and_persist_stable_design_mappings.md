---
id: task_034_001_002
title: Resolve architecture destination and persist stable design mappings
tier: task
status: completed
parent: feat_034_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: fd680bab3618fd7cf4652fff510f9403bfc01fa6
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Resolve architecture destination and persist stable design mappings

## Parent Feature

[feat_034_001](../../features/2_active/feat_034_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend target cascade.toml parsing and RepositoryContext/project context to support [architecture] destination = "target" | "tracking" with target default. Reject tracking without a configured tracking repository and invalid values clearly. Resolve target and tracking DESIGN.md and editable architecture/<immutable-target-repository-key>/ paths. Persist an immutable target repository key and target-code-directory/design-path ownership mapping; never infer identity from a basename on reload. Reuse existing configuration and repository resolver services. Add focused config/path/mapping checks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
