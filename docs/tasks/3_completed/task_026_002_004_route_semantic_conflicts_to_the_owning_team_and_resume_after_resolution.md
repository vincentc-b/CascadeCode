---
id: task_026_002_004
title: Route semantic conflicts to the owning team and resume after resolution
tier: task
status: completed
parent: feat_026_002
children: []
depends_on:
- task_026_002_001
- task_026_002_003
owners:
- swe
skills: []
parent_rev: b2d72c4bb274540f1fa2d709cbdf84ccfcc8407d
created: '2026-10-26'
updated: '2026-10-26'
provider: codex
models:
  swe: gpt-5.6-terra
---
# Route semantic conflicts to the owning team and resume after resolution

## Parent Feature

[feat_026_002](../../features/2_active/feat_026_002.md)

## Depends on

- task_026_002_001
- task_026_002_003

## Objective

Complete the narrow semantic-handoff seam left by task 003: attach an explicit owning-team decision to the existing queued-merge action, accept a linked recorded resolution, and let the normal pending-merge loop resume that same action.

## Scope

- In `cascade.task_rollup`, route a queued task merge's task/code branch conflict to `feature_team` by calling the existing `record_owner_decision` API for the stable `<task_id>:queued_merge` action.
- Provide a small supervisor-facing handoff helper for semantic conflicts whose scope is explicitly known: task/code maps to `feature_team`; cross-feature or epic-contract maps to `epic_team`.
- Derive or require a stable decision identity from the blocked action plus persisted conflict evidence (including source SHA, target SHA, reason, and conflict paths) so repeated supervisor passes do not create duplicate owner decisions.
- Fail closed when the semantic scope is absent or ambiguous. Do not guess an owner and do not mutate Git content.
- Provide a narrow resolution entry point that requires the action id, decision id, and recorded resolution id; validate the linkage through `record_owner_resolution`.
- After the last linked decision is resolved, leave the same action in `retryable` state and retain the existing pending queue entry so `retry_pending_task_merges` invokes the normal merge boundary on the next pass.
- Preserve idempotency across repeated resolution calls and supervisor restarts. Do not mint a replacement action, queue, or task.
- Keep Task worker Git and forge permissions unchanged.

## Acceptance criteria

- A task/code merge conflict creates exactly one `feature_team` owner decision on the existing queued-merge action, with the persisted source/target/conflict evidence.
- An explicitly classified cross-feature or epic-contract semantic conflict creates an `epic_team` owner decision.
- Missing, unknown, or contradictory scope is rejected without selecting an owner or resuming the action.
- While a decision is unresolved, repeated pending-merge passes do not call the merge boundary again and do not duplicate the decision.
- A resolution linked to the same action and decision transitions that action to `retryable`; the next normal supervisor pass retries the original queue entry.
- Replaying the identical resolution is a no-op. A mismatched action, decision, resolution identity, or changed resolution payload is rejected.
- After a successful resumed merge, later supervisor passes do not duplicate merge or rollup.
- Existing mechanical-retry behavior from task 003 remains unchanged.

## Files likely touched

- `cascade/task_rollup.py`
- `cascade/task/action_recovery.py` only if a minimal public validation/helper seam is required
- `tests/task/test_rollup_queue.py`
- `tests/task/test_action_recovery.py` only for focused linkage/idempotency coverage not already present

## Implementation notes

Reuse `record_owner_decision`, `record_owner_resolution`, `load_action`, the stable `<task_id>:queued_merge` action identity, and the existing pending-merge loop. Task 003 already persists the semantic outcome and prevents retries while the action is `awaiting_owner_decision`; this task must populate the owner-decision record and expose resolution-to-retry, not redesign recovery state.

Treat the merge result's ordinary task-branch content conflict as task/code scope. Cross-feature and epic-contract ownership must come from an explicit supervisor classification/caller input; conflict paths alone are not sufficient to infer that broader scope. Resolution records authorize retry only—they do not resolve file content automatically.

## Skills

_(none)_

## Test plan

Add focused supervisor-boundary scenarios proving:

1. a queued task branch conflict records one Feature Team decision with stable identity and full evidence;
2. explicit cross-feature/epic-contract scope records an Epic Team decision;
3. ambiguous scope fails closed;
4. repeated supervision while unresolved neither merges nor duplicates decisions;
5. a linked resolution survives reload/restart, makes the same action retryable, and the next queue pass completes it once;
6. replayed identical resolution is idempotent while mismatched linkage/payload is rejected.

Run the existing `tests/task/test_rollup_queue.py` and `tests/task/test_action_recovery.py` regressions. Broader end-to-end acceptance remains in task 005.

## Out of scope

- Automatic semantic conflict or Git content resolution.
- Inferring epic ownership from filenames or conflict paths.
- A new decision store, merge queue, recovery framework, or general handoff UI.
- Changes to Task worker Git or forge permissions.
- Broad end-to-end recovery coverage assigned to task 005.
