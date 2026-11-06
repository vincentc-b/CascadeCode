---
id: task_032_001_002
title: Integrate recovery dialog with active-work recovery flow
tier: task
status: completed
parent: feat_032_001
children: []
depends_on:
- task_032_001_001
owners:
- swe
skills: []
parent_rev: 69637d05061cdf8b3dbe6c8aa67920cdbaad930b
created: '2026-11-03'
updated: '2026-11-03'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Integrate recovery dialog with active-work recovery flow

## Parent Feature

[feat_032_001](../../features/2_active/feat_032_001.md)

## Depends on

- task_032_001_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Objective

Wire the inventory-backed dialog into eligible provider-blocked active-work rows and the existing human-only recovery endpoint/command.

## Scope

- Make `Change provider` open the modal instead of browser prompts.
- Initialize role selections from the affected Epic, Feature, or Task.
- Construct the existing recovery payload for all affected roles.
- Prevent submission until the replacement is complete and valid, and prevent duplicate submissions while a request is in flight.
- Keep the modal and selections intact on server rejection, with an actionable error.
- On success, close the dialog and refresh the affected row.
- Preserve existing recovery eligibility, lifecycle/checkpoint behavior, child selections, retry behavior, provider setup, and brief authoring.
- Ensure the server remains authoritative and revalidates every affected role through the existing recovery command.

## Done when

Eligible rows complete recovery through the modal and existing endpoint, with correct success, cancellation, in-flight, and rejection behavior and no regression to recovery semantics.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
