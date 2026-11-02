---
id: task_029_003_004
title: Prove provider-recovery lifecycle, restart durability, and isolation
tier: task
status: completed
parent: feat_029_003
children: []
depends_on:
- task_029_003_002
- task_029_003_003
owners:
- swe
skills: []
parent_rev: 8bbd12c5222c3f31a1c067538e89cc5497023f2b
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Prove provider-recovery lifecycle, restart durability, and isolation

## Parent Feature

[feat_029_003](../../features/2_active/feat_029_003.md)

## Depends on

- task_029_003_002
- task_029_003_003

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Add high-signal integration/browser lifecycle proof for the complete recovery flow.

## Coverage
- Activation failure and post-start provider loss.
- Active Epic, active Feature, clean Task, and dirty Task recovery.
- Stale provider/model pins and restored credentials.
- Concurrent recovery attempts and non-stoppable turns.
- Restart durability of blocker/reason/action eligibility.
- No unintended changes to unaffected siblings or children.
- Correct separation of provider setup from eligible Return to backlog.

## Acceptance criteria
- API/browser/restart tests exercise the user-visible recovery journey with minimal mocking.
- Assertions verify durable state, safe reasons, lifecycle transitions, and isolation.
- Tests are focused and non-duplicative; existing lower-level coverage is reused where sufficient.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
