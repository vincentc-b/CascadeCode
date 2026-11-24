---
id: task_032_001_003
title: Add focused recovery-dialog UI and API regression coverage
tier: task
status: completed
parent: feat_032_001
children: []
depends_on:
- task_032_001_002
owners:
- swe
skills: []
parent_rev: 69637d05061cdf8b3dbe6c8aa67920cdbaad930b
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Add focused recovery-dialog UI and API regression coverage

## Parent Feature

[feat_032_001](../../features/2_active/feat_032_001.md)

## Depends on

- task_032_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Add high-signal automated coverage for the inventory-backed provider recovery workflow and verify the existing authoritative server guarantees remain intact.

## Scope

- Cover tier-specific role rendering.
- Cover provider/model dependent revalidation and unavailable saved selections.
- Cover reasoning and flex visibility/support rules.
- Cover valid payload construction, cancellation, retained state after errors, and duplicate-submit prevention.
- Cover loading, empty inventory, and refresh failure where those states are not already exercised.
- Run and, only where required by changed behavior, minimally adjust existing recovery API tests proving authoritative rejection, atomic mutation, and lifecycle safety.

## Done when

Focused UI tests prove the new operator flow, existing recovery API guarantees still pass, and coverage avoids redundant low-value tests of already exercised selector internals.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
