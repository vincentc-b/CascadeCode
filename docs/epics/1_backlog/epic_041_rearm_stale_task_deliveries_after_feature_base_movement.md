---
id: epic_041
title: Rearm stale Task deliveries after Feature-base movement
tier: epic
status: backlog
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-11-07'
updated: '2026-11-07'
provider: codex
flex_mode: false
models:
  epic_manager: gpt-6-astra
  epic_architect: gpt-6-astra
  feature_lead: gpt-6-sol
  feature_architect: gpt-6-sol
  swe: gpt-5.6-sol
reasoning:
  epic_manager: high
  epic_architect: high
  feature_lead: high
  feature_architect: high
  swe: medium
---
# Rearm stale Task deliveries after Feature-base movement

## Intent

Ensure a Task delivery automatically recovers when its final validation becomes stale because the owning Feature branch advances after a transient merge refusal. Queue invalidation must create a new recoverable delivery generation, not replay a cached “already queued” decision for the old Feature base. The supervisor should preserve the existing Task branch and worktree, run fresh supervised validation against the current Feature head, publish replacement delivery evidence, and finish the normal Task-to-Feature merge without human Git or execution-state edits. task_037_003_002 demonstrated the gap: two busy merge attempts were followed by Feature progress, the stale queue was removed, and an ownerless awaiting_merge Task remained stuck because its earlier no-op recovery decision was cached under the same execution attempt.

### Success criteria
1. Detect an active ownerless Task whose queued delivery was invalidated because its deliverable SHA or Feature-base SHA no longer matches current branch heads, including when execution remains awaiting_merge.
2. Give orphan-delivery recovery a durable generation identity that changes when delivery evidence, queue state, deliverable head, or Feature-base head materially changes. A cached no-op or blocker from an older generation must not suppress recovery of the current generation.
3. Revalidate every cached recovery result against current Task status, owner lease, branch heads, delivery evidence, and pending-queue membership before returning it as authoritative. Preserve idempotency for truly identical observations.
4. When the Task branch and worktree remain safe, automatically re-enter the supervised Task validation path against the current Feature head, publish replacement evidence, queue the same Task delivery, and retry the ordinary merge. Never reuse stale validation evidence.
5. Run recovery from supervisor-owned periodic maintenance even when the Feature Team process has exited. The parent recovery tool and periodic sweep must converge on the same serialized operation without duplicate workers, validations, queue entries, or merges.
6. Surface the stale base, invalidated evidence, selected recovery generation, revalidation outcome, and any actionable blocker to the Feature Team and War Room. Do not report merge queued after that queue has been removed.
7. Cover the task_037_003_002 sequence end to end: validated delivery, repeated busy merge refusals, concurrent Feature advancement, stale-evidence invalidation, no live owner, automatic revalidation, and exactly one successful Task merge.
8. Resume the existing Task with its authoritative parent Feature ID from the current Task document. Never pass parent_rev, a commit SHA, or another revision token as the Feature identity used to rebuild checkpoints, graphs, or kickoff context.
9. Exercise the real resume and kickoff path without mocking the callback boundary: a stale delivery with a valid checkpoint starts one correctly pinned Task turn, validates against the current Feature head, replaces evidence, and merges. Assert the resumed graph uses the actual Feature ID and that a mismatched revision cannot initialize a parallel graph.

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints
Build on Epic 027’s durable delivery boundary, orphan-delivery ledger, execution lease, pending merge queue, and direct-report health sweep. Preserve Task branches, worktrees, checkpoints, prior attempts, and action history; do not reset, clean, force-push, or create a replacement Task. Queue invalidation and recovery-generation publication must be atomic or restart-replayable. Do not weaken exact-SHA validation, automatically resolve semantic merge conflicts, add a second scheduler or status store, or require the owning Feature Team process to remain alive. A new generation is permitted only when durable delivery identity or authoritative branch/queue state has materially changed. Recovery tests must cross the real attach, checkpoint, graph, kickoff, supervised-validation, queue, and merge boundaries; mocked callback-only tests are insufficient for identity and liveness guarantees.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-11-07 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
