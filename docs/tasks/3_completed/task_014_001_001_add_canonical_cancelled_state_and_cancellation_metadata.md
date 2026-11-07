---
id: task_014_001_001
title: Add canonical cancelled state and cancellation metadata
tier: task
status: completed
parent: feat_014_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 72e56b3a1a440166537d3ce868251d0a647eba41
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
---
# Add canonical cancelled state and cancellation metadata

## Parent Feature

[feat_014_001](../../features/2_active/feat_014_001.md)

## Depends on

None.

## Acceptance criteria

- The canonical persisted lifecycle/status type accepts `cancelled` for epics, features, and tasks.
- A cancellation transition stores a non-empty reason and a cancellation timestamp; store the actor only if the existing audit model already has an actor field.
- Existing persisted records without cancellation metadata continue to deserialize unchanged.
- A cancelled record serializes and deserializes without losing its status or cancellation metadata at each of the three work tiers.
- This task changes the shared data model and persistence boundary only; the user-facing cancellation command and transition validation belong to task 002.
- At least one focused persistence/model test fails before the implementation and passes after it.

## Files likely touched

- The shared work-item status/lifecycle declaration.
- The shared persisted work metadata/model and its serializer/deserializer.
- Existing model or persistence tests closest to those modules.

Locate the concrete paths in the repository before editing; do not create parallel lifecycle or storage abstractions.

## Implementation notes

Make the smallest backward-compatible model change that represents cancellation consistently across all work tiers. Reuse the existing timestamp and audit conventions. Cancellation metadata must be part of the persisted record, not transient command state.

If the repository already contains the complete model/persistence support described above, do not return a no-op: add or strengthen the focused round-trip test that demonstrates all three tiers, and report the existing implementation path in the task result.

## Skills

_(none)_

## Test plan

- Run the narrow existing test target for work-item model/persistence.
- Add a table-driven or parameterized round-trip case for epic, feature, and task records in `cancelled` state.
- Include a legacy-record case with no cancellation fields.
- Avoid command/API acceptance coverage here; task 003 owns end-to-end lifecycle coverage.

## Out of scope

- Cancellation command/API behavior.
- Rejecting completed work or validating repeated cancellation.
- Downstream cancellation effects and ordering.
- Schema cleanup, migrations unrelated to backward compatibility, or refactors not required by the acceptance criteria.
