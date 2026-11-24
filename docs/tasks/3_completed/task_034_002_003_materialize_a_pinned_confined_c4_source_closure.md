---
id: task_034_002_003
title: Materialize a pinned, confined C4 source closure
tier: task
status: completed
parent: feat_034_002
children: []
depends_on:
- task_034_002_002
owners:
- swe
skills: []
parent_rev: 988e657b67a858b6f997f303624f7b8c375d59b7
created: '2026-11-09'
updated: '2026-11-09'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Materialize a pinned, confined C4 source closure

## Parent Feature

[feat_034_002](../../features/2_active/feat_034_002.md)

## Depends on

- task_034_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Resolve the versioned workspace and its explicit local include closure through feat_034_001 architecture artifact refs. Allow only pinned files under the selected documentation tree, with owner/path provenance and deterministic closure hashing. Reject path escapes, out-of-scope symlinks, cycles, remote includes/assets/themes/extensions, plugins/scripts, and executable exporters before container invocation. Copy only accepted source into an isolated input directory. Add focused positive and adversarial source tests, including traversal and symlink escape. Do not install dependencies or access the network.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
