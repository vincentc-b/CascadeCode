---
id: task_036_001_002
title: Resolve and idempotently prepare local or remote tracking repositories
tier: task
status: completed
parent: feat_036_001
children: []
depends_on:
- task_036_001_001
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
# Resolve and idempotently prepare local or remote tracking repositories

## Parent Feature

[feat_036_001](../../features/2_active/feat_036_001.md)

## Depends on

- task_036_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Implement repository resolution and preparation behind the normalized tracking reference.

## Scope

- Validate local references as usable Git checkouts.
- Map remote references to a deterministic location under Cascade's existing managed-data root, using a stable credential-stripped identity.
- Clone a missing remote checkout with the system Git client; reuse a complete matching checkout; reject or safely recover from incomplete/mismatched state.
- Preserve the user's Git/SSH configuration, environment, and credential helpers. Add no prompt or credential storage.
- Return actionable, credential-redacted diagnostics for invalid paths, non-Git directories, unsupported references, clone failures, and authentication failures.
- Do not add automatic migration, cross-repository transactions, or general multi-repository orchestration.

## Acceptance

- Integration-focused tests with temporary Git repositories prove local validation, deterministic remote placement, first preparation, repeated idempotent preparation, and incomplete/mismatched checkout handling.
- Error tests cover invalid/non-Git local paths and representative clone/authentication failures without leaking user-info, tokens, or helper output.
- A prepared result is returned only after the checkout passes validation.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
