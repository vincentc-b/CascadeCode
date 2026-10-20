---
id: task_083
title: Add optional `cites` field to WorkMeta (feature frontmatter)
tier: task
status: completed
parent: feat_019
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 2c7444bbec5e80b7b6ca1f3f9461475c0d1e4158
created: '2026-10-20'
updated: '2026-10-20'
---
# Add optional `cites` field to WorkMeta (feature frontmatter)

## Parent Feature

[feat_019](../../features/2_active/feat_019.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add `WorkMeta.cites: [str]` (default `[]`, meaningful on features only; empty on epic/task). Serde/parse must accept it and still ignore unknown extra keys; round-trip must preserve it. Keep optional so existing features keep parsing. Add ONE board schema test (parse with/without cites, round-trip, unknown keys still ignored). No linter requiring cites (out of scope). Honors dec_003 (no inferring citations from prose).

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
