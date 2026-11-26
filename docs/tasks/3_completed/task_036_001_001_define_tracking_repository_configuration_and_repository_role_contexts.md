---
id: task_036_001_001
title: Define tracking-repository configuration and repository-role contexts
tier: task
status: completed
parent: feat_036_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 7b76905214502f126fb3c95f58b5d1a95e99412c
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Define tracking-repository configuration and repository-role contexts

## Parent Feature

[feat_036_001](../../features/2_active/feat_036_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add the optional top-level `tracking_repository` setting to TOML and YAML and introduce normalized, explicit target/tracking repository contexts at project initialization.

## Scope

- Parse equivalent TOML and YAML values into one internal tracking-reference type.
- Resolve relative local paths from the configuration file directory, never the process working directory.
- When omitted, alias tracking to the existing target context without changing paths or behavior.
- Make both repository roles explicit for downstream consumers; do not route planning storage in this task.
- Reject syntactically unsupported reference forms with actionable diagnostics that do not expose credentials.

## Acceptance

- Parser/config tests cover TOML/YAML equivalence, omission compatibility, relative-path anchoring, and unsupported values.
- Existing no-setting behavior remains unchanged.
- No credential value is persisted or newly requested.
- The resulting project context exposes distinct named target and tracking roles, even when they alias the same checkout.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
