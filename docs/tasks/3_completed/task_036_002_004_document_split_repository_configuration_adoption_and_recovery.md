---
id: task_036_002_004
title: Document split-repository configuration, adoption, and recovery
tier: task
status: completed
parent: feat_036_002
children: []
depends_on:
- task_036_002_002
owners:
- swe
skills: []
parent_rev: 02eb582fb64d46b4b5181b7e0af494256eebd890
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Document split-repository configuration, adoption, and recovery

## Parent Feature

[feat_036_002](../../features/2_active/feat_036_002.md)

## Depends on

- task_036_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Document the supported operator workflow for routed planning storage.

## Scope

- Configuration and default colocated behavior.
- Local-path and remote tracking-repository references.
- Prerequisite preconfigured Git and SSH access, explicitly excluding credential management.
- Adoption of existing planning artifacts without implying automatic migration.
- Recovery from interrupted preparation or synchronization and interpretation of failure states.

## Acceptance criteria

- Documentation includes concise split-mode and colocated examples.
- Repository roles and artifact placement are unambiguous.
- Prerequisites, non-goals, adoption steps, and recovery procedures match implemented behavior.
- Examples do not promise cross-repository transactions or automatic migration.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
