---
id: task_026_002_005
title: Verify supervisor recovery and handoff acceptance scenarios
tier: task
status: completed
parent: feat_026_002
children: []
depends_on:
- task_026_002_002
- task_026_002_003
- task_026_002_004
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
# Verify supervisor recovery and handoff acceptance scenarios

## Parent Feature

[feat_026_002](../../features/2_active/feat_026_002.md)

## Depends on

- task_026_002_002
- task_026_002_003
- task_026_002_004

## Objective

Prove the integrated feature contract with a compact supervisor-level acceptance suite.

## Scope

- Exercise the real supervisor orchestration boundary and durable action store introduced or extended by tasks 001–004.
- Cover interrupted Task resumption, missing integration-checkout repair followed by queued-merge retry, semantic ownership routing, and linked-resolution resumption.
- Verify restart and repeated-evaluation idempotency for the same persisted action identity.
- Assert the existing Task-worker Git and forge permission boundary remains unchanged.
- Reuse existing test fixtures and helpers; extend production code only if a test exposes a defect in the approved feature behavior.

## Acceptance criteria

- A persisted interrupted Task action is reloaded and resumed to completion without minting a replacement action; a repeated supervisor pass does not execute completed work again.
- A missing integration checkout is recreated from authoritative repository/ref metadata and the original queued merge action is retried. Re-evaluation after repair does not create another checkout or merge action.
- A mechanically blocked queued merge is retried under the same stable action identity after its deterministic precondition is repaired.
- A task/code semantic conflict persists a decision-blocked action owned by the Feature Team and is not auto-resolved or retried while unresolved.
- A cross-feature or epic-contract conflict persists a decision-blocked action owned by the Epic Team and is not auto-resolved or retried while unresolved.
- An explicit resolution linked to the blocked action makes that exact action runnable; after reconstructing the supervisor from durable state, it resumes once and can complete.
- Missing, stale, mismatched, or ambiguously owned resolution data fails closed and leaves the action decision-blocked.
- Tests demonstrate that Task workers receive no new Git or forge capability.
- The narrow supervisor acceptance suite and relevant existing regressions pass.

## Files likely touched

- Existing supervisor integration/acceptance test module(s) covering lifecycle recovery and merge supervision.
- Existing test fixtures/helpers for durable lifecycle actions, integration checkouts, queued merges, and recorded resolutions.
- Production files from tasks 001–004 only if the integrated scenarios reveal a contract defect.

Locate the concrete repository paths with `rg` before editing; do not create a parallel test harness when an existing supervisor suite can be extended.

## Implementation notes

Model each scenario through persisted state and the supervisor entry point, then assert observable state transitions and side-effect counts. Simulate restart by constructing a fresh supervisor/store view over the same durable records. Prefer table-driven ownership cases where that improves clarity. Avoid mocking internal helper calls when filesystem/repository fixtures and persisted records can exercise the boundary economically.

Keep assertions focused on stable action identity, final state, owner tier, resolution linkage, and non-duplication. Do not broaden this task into persistence, merge, workflow, or permission redesign.

## Skills

_(none)_

## Test plan

1. Run the narrow supervisor recovery/handoff test module while developing.
2. Run the existing supervisor/lifecycle regression group that covers Task execution and queued feature merges.
3. Include explicit repeated-evaluation and fresh-supervisor restart passes in the acceptance scenarios.
4. If repository/checkout fixtures are used, assert the restored checkout matches authoritative repository/ref identity and cleanup remains deterministic.
5. Report the exact commands and outcomes in the implementation handoff.

## Out of scope

- New recovery or routing behavior beyond the feature contract.
- Automatic semantic conflict resolution.
- A new test framework or broad fixture refactor.
- Redundant unit tests for helpers already exercised by these supervisor-level scenarios.
- Changes to Task-worker Git or forge permissions.
