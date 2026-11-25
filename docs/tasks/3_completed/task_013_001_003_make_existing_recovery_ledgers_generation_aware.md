---
id: task_013_001_003
title: Make existing recovery ledgers generation-aware
tier: task
status: completed
parent: feat_013_001
children: []
depends_on:
- task_013_001_001
owners:
- swe
skills: []
parent_rev: e42512edf87a275dc4c15513cf66b40350b9ad28
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Make existing recovery ledgers generation-aware

## Parent Feature

[feat_013_001](../../features/2_active/feat_013_001.md)

## Depends on

- task_013_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Outcome
Extend remediation dispositions, Task action recovery, orphan delivery, and relevant review recovery records to carry one typed incident contract. Preserve existing authoritative lifecycle and attempt history; add no second status database.

## Acceptance
- Each incident records typed work ID/tier, concrete accountable owner, failure class, authoritative generation and evidence, selected capability, request/acknowledgement/result, attempts, cooldown, and outcome.
- Relevant lease, branch head, queue membership, validation/checkpoint, document revision, parent blockage, and capability changes alter the fingerprint.
- Only terminal success for an unchanged generation suppresses permanently. Claimed, error, refused, deferred, unsafe, and no-op outcomes expire or re-evaluate within finite retry policy; interrupted claims replay safely.
- Existing ledger rows remain readable, and history survives later generations.

## Validation
Use focused ledger integration cases for generation changes, crash expiry, repeated observations, and old rows.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
