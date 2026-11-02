---
id: task_029_003_002
title: Implement human-only provider change and retry recovery controls
tier: task
status: completed
parent: feat_029_003
children: []
depends_on:
- task_029_003_001
owners:
- swe
skills: []
parent_rev: 2fae02f2bc0a1be42fae4a50e1e0a9e174476035
created: '2026-11-02'
updated: '2026-11-02'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-terra
---
# Implement human-only provider change and retry recovery controls

## Parent Feature

[feat_029_003](../../features/2_active/feat_029_003.md)

## Depends on

- task_029_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Implement server-side recovery actions using the existing provider/model controls.

## Scope
- Expose human-only Change provider and Retry actions.
- Route provider setup separately when credentials/configuration are missing.
- Offer Return to backlog only when the lifecycle state is eligible.
- Enforce concurrency/idempotency guards and refuse unsafe action during non-stoppable turns.
- Support active Epic, active Feature, and clean/dirty Task recovery without disturbing siblings or children.

## Acceptance criteria
- Authorization and lifecycle eligibility are enforced server-side.
- Retry after restored credentials resumes safely.
- Stale pins and concurrent requests produce deterministic, safe outcomes.
- Focused API tests cover success, refusal, concurrency, and isolation paths.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
