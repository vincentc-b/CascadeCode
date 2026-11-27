---
id: task_035_003_003
title: Align Feature and Epic Team provider recovery contracts
tier: task
status: completed
parent: feat_035_003
children: []
depends_on:
- task_035_003_002
owners:
- swe
skills: []
parent_rev: de399fe429b89cf9bf3c8061b0ddfbccfad896e0
created: '2026-11-04'
updated: '2026-11-04'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Align Feature and Epic Team provider recovery contracts

## Parent Feature

[feat_035_003](../../features/2_active/feat_035_003.md)

## Depends on

- task_035_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Scope

Update every supported Feature/Epic Team provider launcher and result-reporting adapter to expose the same restart-safe conflict-resolution capability and normalized result contract.

## Required outcomes

- All supported providers launch the same action identity/checkpoint inputs.
- Resume, retry, completed, and blocker results have provider-independent semantics and required evidence.
- Provider-specific retries cannot duplicate workflow side effects.
- Contract-level tests cover meaningful provider differences with a shared fixture/table where practical.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
