---
id: task_079
title: 'War Room View plan deep-link to #plan-comments'
tier: task
status: backlog
parent: feat_016
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: ddca58f8a69048ff10e27fb9a4df206ac71467b0
created: '2026-10-19'
updated: '2026-10-19'
---
# War Room View plan deep-link to #plan-comments

## Parent Feature

[feat_016](../../features/2_active/feat_016.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Point the existing View plan control on epic and feature rows at /plan/{id}#plan-comments. No second compose form, no extra Comments button; leave existing toasts for new human comments unchanged. Tasks keep current behavior.

Verification: smoke check (open War Room, click View plan on an epic and a feature row, confirm URL and anchor). No unit test.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
