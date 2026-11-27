---
id: task_037_003_004
title: Implement human authorization and durable action receipt
tier: task
status: completed
parent: feat_037_003
children: []
depends_on:
- task_037_003_002
- task_037_003_003
owners:
- swe
skills: []
parent_rev: fe9726020dd8a55655271e35ba3e06915a9f5905
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Implement human authorization and durable action receipt

## Parent Feature

[feat_037_003](../../features/2_active/feat_037_003.md)

## Depends on

- task_037_003_002
- task_037_003_003

## Acceptance criteria

- Persist an opaque failed-action attempt ID and original replay context at each canonical provider-preflight failure; a mutable work-item blocker or read-only preview cannot stand in for that identity.
- Accept continuation only from a server-authenticated human principal with the exact failed-action reference, expected source revision and complete selection fingerprint. Agent, scheduler, refresh and automatic retry callers receive a structured refusal.
- Under the lifecycle transition gate and serialized ledger boundary, re-read the attempt, documents and lifecycle state; refresh inventory and validate the entire same selection with effective Flex disabled. Reject stale, mixed or otherwise blocked selection before writing a waiver.
- Atomically commit human authorization, the scoped waiver and one receipt keyed by failed-action ID, kind/target, original revision and selection fingerprint. Repeated or concurrent requests find that receipt.
- Persist `authorized` and `handoff_pending` as separate restart-safe transitions. After a pending claim, duplicate clicks and restart cannot invoke the original action again; uncertain results remain `ambiguous` until durable evidence resolves them.
- Return safe structured receipt/refusal data without credentials, provider error bodies or raw secrets. Preserve reviewed plan hashes, approvals and dirty worktrees.

## Files likely touched

`cascade/provider_recovery_command.py`, `cascade/provider_recovery.py`, the provider recovery ledger and canonical failed-preflight boundaries.

## Implementation notes

Use the feature API contract as the source of truth for action identity, waiver scope and receipt transitions. Task 5 supplies the narrow replay adapters and decisive handoff reconciliation.

## Skills

_(none)_

## Test plan

Focused command/ledger tests for human-only authorization, stale selection and inventory, distinct attempts on one work item, concurrent claims and restart before/after pending. Task 6 covers end-to-end replay.

## Out of scope

Changing reviewed provider/model/reasoning pins, replaying lifecycle actions, or reconstructing graph checkpoints.
