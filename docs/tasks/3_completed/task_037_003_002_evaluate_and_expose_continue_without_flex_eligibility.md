---
id: task_037_003_002
title: Evaluate and expose Continue without Flex eligibility
tier: task
status: completed
parent: feat_037_003
children: []
depends_on:
- task_037_003_001
owners:
- swe
skills: []
parent_rev: 8bb76119d1cabb729e4ff6e9c7a855a074319204
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Evaluate and expose Continue without Flex eligibility

## Parent Feature

[feat_037_003](../../features/2_active/feat_037_003.md)

## Depends on

- task_037_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Extend recovery state and command/API presentation so the action appears only for a concrete failed original action with at least one Flex rejection, exclusively flex_mode_not_supported deterministic failures, and a fresh full-selection validation with Flex disabled that passes. Keep transient, configuration, provenance, capability, lifecycle and approval blockers visible. Reject agent, scheduler, refresh and automatic-retry authorization at the command boundary. Return structured reasons without secret data.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
