---
id: task_028_003_002
title: Cover epic close-review controls with browser tests
tier: task
status: completed
parent: feat_028_003
children: []
depends_on:
- task_028_003_001
owners:
- swe
skills: []
parent_rev: a73db3bbb1b416c3bb236effec3b027815958aaf
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
---
# Cover epic close-review controls with browser tests

## Parent Feature

[feat_028_003](../../features/2_active/feat_028_003.md)

## Depends on

- task_028_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective
Add high-signal browser coverage for the integrated epic close-review experience.

## Acceptance criteria
- Verify the implementation-review link is accessible and opens through the safe external-link behavior.
- Verify pending state and its review link survive refresh and navigation, and cover restart persistence using the existing browser-test fixture/harness where supported.
- Verify actionable blocker messaging and the manual `Finish close` path when automatic reconciliation is unavailable.
- Verify successful completion removes/replaces pending controls with the completed state.
- Assert forge-supplied display text remains escaped rather than interpreted as HTML.

## Testing approach
Prefer focused end-to-end scenarios and existing fixtures over redundant mock-heavy unit tests.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
