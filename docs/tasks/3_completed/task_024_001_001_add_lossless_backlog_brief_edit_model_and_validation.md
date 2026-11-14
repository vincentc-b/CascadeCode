---
id: task_024_001_001
title: Add lossless backlog brief edit model and validation
tier: task
status: completed
parent: feat_024_001
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 330b210202ab7304106209c3e0c7354250ca6555
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
models:
  swe: gpt-5.6-luna
---
# Add lossless backlog brief edit model and validation

## Parent Feature

[feat_024_001](../../features/2_active/feat_024_001.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Create the shared read/validate/render foundation for editing an existing backlog epic brief without regenerating it from the new-brief template.

## Scope

- Extend the existing brief stack to load persisted authoring values for title, intent, success criteria, constraints, provider, and model/reasoning assignments for epic_manager, epic_architect, feature_lead, feature_architect, and swe.
- Preserve all other human-authored Markdown sections, original ID/path, creation metadata, lifecycle state, and unrelated metadata.
- Define the editable-versus-system-managed boundary so generated approval/runtime metadata and graph bookkeeping cannot be changed through this flow.
- Reuse current provider/model inventory and validation; retain unsupported or unavailable saved assignments for display and report them explicitly rather than substituting defaults.
- Represent an explicitly cleared reasoning override distinctly from an unchanged value.
- Carry explicit source provenance sufficient to compare the target brief revision, not the entire trunk revision.
- Detect unchanged submissions after normalization.

## Acceptance

- Round-tripping an existing brief with no edits is byte-stable or produces no write.
- Editing every supported field plus arbitrary extra Markdown changes only the intended content while preserving identity, path, creation metadata, untouched content, and system-managed fields.
- Unsupported saved assignments remain visible; invalid new assignments are rejected without discarding entered values.
- Tests focus on parsing/rendering/validation boundaries not already covered by higher-level coverage.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
