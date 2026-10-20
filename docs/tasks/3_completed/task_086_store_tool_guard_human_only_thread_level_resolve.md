---
id: task_086
title: 'Store + tool guard: human-only thread-level resolve'
tier: task
status: completed
parent: feat_018
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 9d347c8004ae429d56cac63dbc289813b3d1a6e9
created: '2026-10-20'
updated: '2026-10-20'
---
# Store + tool guard: human-only thread-level resolve

## Parent Feature

[feat_018](../../features/2_active/feat_018.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Change `cascade.comments.store.resolve_comment` to require `author="human"` (agents fail closed with `ResolveNotAllowed`) and refuse non-roots (`NotARoot`). Cascade: rewrite the root and every row whose `parent` chain reaches it to `state=resolved` in `docs/_comments/{doc_id}.jsonl` (rewrite in place, no duplicate rows, no deletion). Reconstructed frozen `Comment` must copy feat_016 fields (`line_start`, `line_end`, `doc_sha`, `blocks`). Emit `CommentResolved` once for the root. Unregister `resolve_comment` from epic and feature planning tool registries (or keep name and always raise); agents keep `reply_comment`. Already-resolved root is idempotent (no error).

Tests (store-level, high-signal): human resolve cascades to a human reply that would otherwise stay open and block closeout; agent author raises ResolveNotAllowed; reply id raises NotARoot; agent tool registries do not expose resolve. Optional: `record_decision` body convention `In reply to: cmt_NNN` is a playbook line only, not a task.

Acceptance: spec feat_018 Scope/In bullets 2-3; D1, D4, D5.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
