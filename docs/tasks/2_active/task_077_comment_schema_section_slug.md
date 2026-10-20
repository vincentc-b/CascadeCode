---
id: task_077
title: Comment schema + section_slug()
tier: task
status: blocked
parent: feat_016
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 3b458593a747105eb2f1818ef034b76e21512e41
created: '2026-10-19'
updated: '2026-10-20'
---
# Comment schema + section_slug()

## Parent Feature

[feat_016](../../features/2_active/feat_016.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add optional line_start, line_end, doc_sha, blocks (list[work_id], default empty) to cascade.comments.types.Comment, store.comment() kwargs, and from_dict (missing keys -> None/[]); to_dict always emits them. Comment is frozen: update every constructor (_append_comment, resolve_comment rewrite, tests) to copy the new fields.

Add cascade.comments.section_slug(heading) -> str: trim, lowercase, non [a-z0-9] -> '-', collapse repeats, strip leading/trailing '-'. Hyphenated; do NOT reuse cascade.board.paths.slugify or cascade.amendments.store.section_slug (underscores).

Tests (high-signal only): legacy sidecar row without new keys round-trips; one section_slug vector table (e.g. 'Memory layout' -> 'memory-layout') that fails if underscores are used. Do not rewrite historical sidecars.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
