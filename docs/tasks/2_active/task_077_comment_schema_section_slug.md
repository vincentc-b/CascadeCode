---
id: task_077
title: Comment schema + section_slug()
tier: task
status: active
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
# Comment schema + section_slug()

## Parent Feature

[feat_016](../../features/2_active/feat_016.md)

## Depends on

None.

## Acceptance criteria

- `cascade.comments.types.Comment`, `cascade.comments.store.comment()` and `from_dict` accept optional `line_start` (int|None), `line_end` (int|None), `doc_sha` (str|None) and `blocks` (list of work ids, default `[]`).
- `from_dict` treats missing keys as `None` / `[]`, so legacy sidecar rows load unchanged.
- `to_dict` always emits all four keys.
- Every `Comment(...)` constructor copies the new fields, including `_append_comment`, the `resolve_comment` rewrite, and any test helpers. `Comment` is frozen, so a missed constructor silently drops data.
- New `cascade.comments.section_slug(heading: str) -> str` is importable from the package: trim, lowercase, non `[a-z0-9]` runs become a single `-`, strip leading/trailing `-`. `"Memory layout"` -> `"memory-layout"`. It never emits `_`.
- It does NOT reuse or import `cascade.board.paths.slugify` or `cascade.amendments.store.section_slug` (those use underscores).
- The change is real code committed on the task branch. A diff with only markdown is a failure.

## Files likely touched

- `cascade/comments/types.py`
- `cascade/comments/store.py`
- `cascade/comments/__init__.py` (export `section_slug`) or a new `cascade/comments/slug.py` re-exported from it
- `tests/` comment store / slug tests (find the existing comments store test module and extend it)

## Implementation notes

Add optional line_start, line_end, doc_sha, blocks (list[work_id], default empty) to cascade.comments.types.Comment, store.comment() kwargs, and from_dict (missing keys -> None/[]); to_dict always emits them. Comment is frozen: update every constructor (_append_comment, resolve_comment rewrite, tests) to copy the new fields.

Add cascade.comments.section_slug(heading) -> str: trim, lowercase, non [a-z0-9] -> '-', collapse repeats, strip leading/trailing '-'. Hyphenated; do NOT reuse cascade.board.paths.slugify or cascade.amendments.store.section_slug (underscores).

Do not rewrite historical sidecars. Do not validate `blocks` ids against the board.

## Skills

_(none)_

## Test plan

High-signal tests only, no mock-heavy unit tests:

1. Legacy round-trip: write a sidecar JSONL row without `line_start`, `line_end`, `doc_sha`, `blocks`; load it through the store; assert `None`/`None`/`None`/`[]`; resolve it (exercises the `resolve_comment` rewrite) and assert the new fields survive.
2. New-field round-trip: `store.comment(..., line_start=3, line_end=5, doc_sha="abc", blocks=["task_001"])` then reload and assert equality.
3. One `section_slug` vector table, for example `"Memory layout"` -> `"memory-layout"`, `"  Open  questions "` -> `"open-questions"`, `"A_b/C"` -> `"a-b-c"`, `"--x--"` -> `"x"`. Add an assertion that no result contains `_`, so the table fails if the wrong slugger is used.

Run the comments test module and confirm it passes before finishing.

## Out of scope

- HTTP/POST changes (task_078).
- War Room UI (task_079).
- Resolve behavior changes, rewriting historical section strings, validating `blocks` ids.
- Changing `cascade.board.paths.slugify` or `cascade.amendments.store.section_slug`.
