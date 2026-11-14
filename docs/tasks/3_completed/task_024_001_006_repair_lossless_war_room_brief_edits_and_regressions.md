---
id: task_024_001_006
title: Repair lossless War Room brief edits and regressions
tier: task
status: completed
parent: feat_024_001
children: []
depends_on:
- task_024_001_005
owners:
- swe
skills: []
parent_rev: c885a1b5d9e0ed694f13e4c89de4767b84f9bce2
created: '2026-10-25'
updated: '2026-10-25'
provider: codex
models:
  swe: gpt-5.6-luna
---
# Repair lossless War Room brief edits and regressions

## Parent Feature

[feat_024_001](../../features/2_active/feat_024_001.md)

## Depends on

- task_024_001_005

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Intent

Close the remaining acceptance blockers in the merged backlog-brief edit flow without expanding feature scope.

## Scope

- Initialize edit mode from the selected brief's saved provider, per-role models, and reasoning, including saved values unavailable in current inventory.
- Submit the user's edited provider/model/reasoning selection; attach only epic identity and source provenance from the original target. Do not overwrite edited assignments with the saved originals.
- Carry `additional_markdown` through request validation and rendering so human-authored sections can be changed without losing untouched content.
- Make stale/reload recovery actionable while preserving entered form values.
- Add focused regressions for the fetched-trunk provenance check, failed snapshot replacement rollback, edit-mode prefill/submission (including clearing reasoning and unavailable saved values), and editable additional Markdown. Prefer a compact UI/API/integration suite; do not add a second broad mock-heavy suite.

## Acceptance criteria

- Editing and submitting provider, all role models, reasoning overrides/clears, and additional Markdown produces the requested one-file brief diff while preserving identity, path, lifecycle, metadata, and untouched content.
- Saved unavailable assignments remain visible and unchanged unless the user explicitly selects a valid replacement.
- A stale response offers an explicit reload path and does not silently discard entered work.
- A newer fetched-trunk brief is rejected even when the local copy matches the submitted revision.
- If snapshot publication fails after moving the prior snapshot, the prior valid snapshot remains readable.
- Focused automated tests fail against the current merged behavior and pass with the repair; existing create-brief coverage remains green.

## Non-goals

No active/completed-plan editing, generic Markdown/YAML editor, pending-PR manager, new provider inventory behavior, or general branch reconciliation.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
