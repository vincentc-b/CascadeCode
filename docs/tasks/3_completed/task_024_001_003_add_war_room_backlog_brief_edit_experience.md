---
id: task_024_001_003
title: Add War Room backlog brief edit experience
tier: task
status: completed
parent: feat_024_001
children: []
depends_on:
- task_024_001_002
owners:
- swe
skills: []
parent_rev: 90cda45b486fd8f2c1b3900a30e6707d495bd908
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
models:
  swe: gpt-5.6-luna
---
# Add War Room backlog brief edit experience

## Parent Feature

[feat_024_001](../../features/2_active/feat_024_001.md)

## Depends on

- task_024_001_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Expose a safe, recoverable Edit flow for eligible backlog epic briefs in War Room.

## Scope

- Show Edit only for eligible backlog epic briefs; do not expose this flow for active or completed plans.
- Reuse the existing brief dialog and provider/model selectors, but prefill from the selected brief's persisted values rather than create-form defaults.
- Support all authoring fields and preserve/edit additional human-authored Markdown sections.
- Keep unavailable or unsupported saved provider/model/reasoning assignments visible without silently replacing them.
- Allow reasoning overrides to be explicitly cleared.
- Submit the source provenance returned by the read route.
- Preserve all entered work on validation, stale-target, network, Git, or forge errors; present reload or retry guidance appropriate to the failure.
- Disable duplicate submission while a request is in flight.
- Treat cancel and no-op as non-creating outcomes; display a real PR/MR link only when creation has succeeded.

## Acceptance

- The dialog accurately prefills every persisted editable value, including extra Markdown and unavailable saved assignments.
- Validation and submission failures retain input, and stale/non-backlog responses prompt a reload.
- Double-submit cannot create duplicate requests; cancel/no-op creates no review.
- Successful submission surfaces the returned review link without locally changing or activating the board item.
- Focused UI/API integration checks cover prefill, reasoning clear, error recovery, duplicate guard, no-op, and success.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
