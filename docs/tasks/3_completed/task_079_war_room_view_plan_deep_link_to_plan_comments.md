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

- On epic and feature rows, the existing View plan control links to `/plan/{id}#plan-comments`.
- Task rows keep their current View plan behavior.
- No compose form and no extra Comments button are added; existing toasts for new human comments are unchanged.
- The change is real code committed on the task branch (currently `war_room.js` builds `"/plan/" + item.id`). A diff with only markdown is a failure.

## Files likely touched

- `cascade/war_room/static/war_room.js` (locate with `rg '"/plan/"'`; the View plan href is built there)
- Any template or test that asserts the old href, if one exists

## Implementation notes

Point the existing View plan control on epic and feature rows at /plan/{id}#plan-comments. No second compose form, no extra Comments button; leave existing toasts for new human comments unchanged. Tasks keep current behavior.

Verification: smoke check (open War Room, click View plan on an epic and a feature row, confirm URL and anchor). No unit test.

## Skills

_(none)_

## Test plan

Smoke check only, no new unit test. Record the result in the final message:

1. Grep confirms the href for epic/feature rows ends with `#plan-comments` and task rows are unchanged.
2. If a War Room server can be started locally, load the page and confirm the View plan URL on one epic row and one feature row. Otherwise state that only the static check was done.
3. If an existing test asserts the old href, update it; do not add new tests.

## Out of scope

- Gutter, text-selection, re-anchor, or outdated UI (feat_017).
- Any new compose form or Comments button.
- Changes to toasts or to task-row behavior.
