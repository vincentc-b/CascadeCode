---
id: task_036_001_003
title: Integrate repository resolution at startup and prove compatibility contracts
tier: task
status: completed
parent: feat_036_001
children: []
depends_on:
- task_036_001_002
owners:
- swe
skills: []
parent_rev: fb178cc6d170fa0b2aa8cef14fcd0d3faa249740
created: '2026-11-06'
updated: '2026-11-06'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Integrate repository resolution at startup and prove compatibility contracts

## Parent Feature

[feat_036_001](../../features/2_active/feat_036_001.md)

## Depends on

- task_036_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Wire tracking-repository resolution into project startup so downstream services receive validated target and tracking contexts, while preserving the current default path.

## Scope

- Run configuration normalization and repository preparation before project initialization reports success.
- Pass/retrieve the resolved role contexts explicitly; do not infer either role from the current working directory after initialization.
- Keep source/worktree/build behavior on the target context.
- Expose the tracking context for the dependent planning-lifecycle feature without switching those consumers here.
- Ensure startup failures identify the affected tracking reference and remediation while redacting credentials.

## Acceptance

- A high-signal startup/integration scenario proves omitted configuration aliases tracking to target with existing compatibility behavior.
- TOML and YAML split-mode scenarios prove the same resolved tracking checkout and explicit distinct contexts.
- Failure scenarios prove invalid/unavailable tracking repositories stop startup before false success.
- Existing project-startup and target-worktree tests remain green; no planning-lifecycle routing or documentation work from Feature 2 is pulled into scope.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
