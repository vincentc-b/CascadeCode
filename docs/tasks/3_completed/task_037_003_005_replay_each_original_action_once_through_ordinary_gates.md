---
id: task_037_003_005
title: Replay each original action once through ordinary gates
tier: task
status: completed
parent: feat_037_003
children: []
depends_on:
- task_037_003_004
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
# Replay each original action once through ordinary gates

## Parent Feature

[feat_037_003](../../features/2_active/feat_037_003.md)

## Depends on

- task_037_003_004

## Acceptance criteria

- Invoke only the original failed action with its persisted actor and arguments: Epic activation, Feature dispatch, the specific approval-released Feature/Task dispatch target, or Task retry.
- Enter through the existing canonical gate for each action, including dependency, review, approval, lifecycle, worktree and fresh execution preflight checks. A new refusal records `blocked` with its structured reason and keeps the incident actionable.
- Claim `handoff_pending` durably before invoking an action. Repeated/concurrent requests and restart never make a second invocation after that claim.
- Carry the authorized Flex waiver across a canonical status relocation or Task parent-pin refresh only through a durable lineage entry bound to that receipt and pending claim. Record exact before/after paths, revisions and selection fingerprints; verify unchanged provider, model, reasoning, requested Flex and role scope. Persist the entry before kickoff. Later edits, unrecorded relocations and independent child overrides cannot inherit it.
- Mark `completed` only with decisive durable evidence of both the lifecycle effect and turn handoff. An emitted event alone is insufficient when kickoff may still be in the process-local deferred queue. Reconcile an uncertain handoff against durable evidence; otherwise retain `ambiguous` and surface an actionable incident.
- Preserve prior successful lifecycle steps, approvals, plan hashes and dirty worktrees. The normal successful path produces at most one lifecycle event and one model turn.

## Files likely touched

Canonical activation/dispatch/retry adapters, provider recovery command and receipt ledger, waiver lineage at the canonical document transition boundary, and durable kickoff/turn evidence.

## Implementation notes

Use the receipt and action reference from task 4. Do not redo an approval already committed, dispatch unrelated children, invoke a model turn directly, or reconstruct an opaque graph checkpoint. If existing kickoff evidence cannot prove a handoff across restart, leave the receipt ambiguous rather than retrying. The feature API contract's canonical waiver carry-forward rule applies to both status relocation and Task parent-pin refresh.

## Skills

_(none)_

## Test plan

Focused integration checks for all four action adapters, ordinary gate refusals, duplicate/restart behavior, event-before-kickoff ambiguity and one successful event/turn. Cover waiver carry-forward through canonical status movement and Task parent-pin refresh, plus invalidation by a later edit or independent child override. Task 6 owns the broader command/API matrix.

## Out of scope

Broad lifecycle refactors or recovery of unrelated provider errors.
