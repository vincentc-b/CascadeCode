---
id: task_079
title: 'War Room View plan deep-link to #plan-comments'
tier: task
status: completed
parent: feat_016
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 6a9092f322a947e128f1ddfd9a643f8e37049273
created: '2026-10-19'
updated: '2026-10-20'
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
