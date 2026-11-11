---
id: task_046_002_003
title: Wire live semantic discussion into the paired review page
tier: task
status: completed
parent: feat_046_002
children: []
depends_on:
- task_046_002_001
- task_046_002_002
owners:
- swe
skills: []
parent_rev: c56b95900e11c7c1174d35d7c1af1b8fccec142f
created: '2026-11-10'
updated: '2026-11-10'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Wire live semantic discussion into the paired review page

## Parent Feature

[feat_046_002](../../features/2_active/feat_046_002.md)

## Depends on

- task_046_002_001
- task_046_002_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Use the shared viewer's semantic selection and the authorized thread HTTP contract to create requirement/view/element/relationship roots from the live plan review. Show target, side, repository and full pinned revision before submit. Render replies, incoming refresh, authorized resolve/reopen and outdated blocking status without losing drafts or selection; old-tab drafts require explicit review after tuple replacement. Keep Markdown threads available. Test a real-page create/reply/resolve/reopen/reload flow against the running server, including incoming updates and narrow-screen usability.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
