---
id: task_034_007_002
title: Assign design ownership and reconstruct leaf designs and C4 model
tier: task
status: completed
parent: feat_034_007
children: []
depends_on:
- task_034_007_001
owners:
- swe
skills: []
parent_rev: c57403e2106201d81c35a0c4cf7056f9ea5a23a3
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Assign design ownership and reconstruct leaf designs and C4 model

## Parent Feature

[feat_034_007](../../features/2_active/feat_034_007.md)

## Depends on

- task_034_007_001

## Acceptance criteria

- Consume Task 001's exact inventory baseline and gap list. Resolve the target and tracking design destination from ProjectContext; retain the target repository key and inventory digest in the mapping and design evidence.
- Map every meaningful target-code directory to exactly one editing owner in the schema-v1 design index. Give every excluded directory a covering parent; keep root `.` and its DESIGN.md. Assign each shared model fragment one owner.
- Deliver actual, concise leaf DESIGN.md files for included directories, grounded in inspected current code/tests and historical evidence. Each states purpose, important interfaces, owned requirement/decision IDs and citations, and known gaps. Cancelled or superseded plans alone do not establish current design.
- Deliver an initial C4 workspace with stable element/view IDs and at least the context, container, and relevant component views needed for the inspected code. Keep model references aligned with leaf designs and a single home for each requirement/decision ID.
- Stage owned design/model bytes through the exact-revision proposal path; route ancestor/shared edits to their owner. Record pending reviews and material evidence gaps instead of treating staged content as accepted.

## Files likely touched

- Configured target architecture destination: design-mappings.json, root and leaf DESIGN.md files, workspace/model/views DSL and model contract.
- Focused tests or validation fixtures for mapping coverage and stable model references, if existing checks do not cover them.

## Implementation notes

Use Task 001's pinned inventory to allocate owners before editing. Verify historical leads against current code/tests. Preserve configured paths and F/C proposal contracts; do not bypass one-owner review or mutate tracking-only architecture as a substitute for target design.

## Skills

_(none)_

## Test plan

Run focused mapping coverage and reference checks on the actual target tree. Validate the authored DSL with the already pinned Structurizr image and inspect the exported JSON/SVG for the created views. Report exact revisions and any blocked proposal/coverage items.

## Out of scope

Final ancestor/interface reconciliation, late-delta closeout, and full final acceptance belong to Tasks 003 and 004.
