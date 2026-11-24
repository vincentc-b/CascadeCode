---
id: task_037_004_004
title: Validate provider readiness and recovery across War Room browser and API flows
tier: task
status: completed
parent: feat_037_004
children: []
depends_on:
- task_037_004_003
owners:
- swe
skills: []
parent_rev: 17dac781a1b3789bee7ff452d6dfbd00b6f91759
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Validate provider readiness and recovery across War Room browser and API flows

## Parent Feature

[feat_037_004](../../features/2_active/feat_037_004.md)

## Depends on

- task_037_004_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Using the existing browser harness and fake provider inventory, cover invalid future Feature/SWE role at Epic activation; every failed role and remedy; successful Continue without Flex replay with unchanged reviewed plan; transient/setup versus deterministic rejection; stale inventory refreshed; catalog drift after activation blocked at launch; approval-driven partial failures and Task retry. Assert lifecycle side-effect counts server-side and keyboard/focus behavior in browser. Run targeted existing recovery/readiness/brief/approval regression suites. Keep tests high-signal and do not install dependencies.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
