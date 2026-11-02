---
id: task_030_001_002
title: Enforce authorized return command and API contract
tier: task
status: completed
parent: feat_030_001
children: []
depends_on:
- task_030_001_001
owners:
- swe
skills: []
parent_rev: 31fc2f4ce7bc59019dba554db3ec4802e9e955f3
created: '2026-11-01'
updated: '2026-11-01'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Enforce authorized return command and API contract

## Parent Feature

[feat_030_001](../../features/2_active/feat_030_001.md)

## Depends on

- task_030_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add the human-authorization requirement and return API/command contract. Gate execution through the shared evaluator, return stable refusal reasons, and ensure refused requests do not mutate substantive state.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
