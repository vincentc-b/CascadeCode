---
id: task_084
title: Implement blocking_threads_for + is_section_thread in cascade/comments/gate.py
tier: task
status: completed
parent: feat_019
children: []
depends_on:
- task_083
owners:
- swe
skills: []
parent_rev: 2c7444bbec5e80b7b6ca1f3f9461475c0d1e4158
created: '2026-10-20'
updated: '2026-10-20'
---
# Implement blocking_threads_for + is_section_thread in cascade/comments/gate.py

## Parent Feature

[feat_019](../../features/2_active/feat_019.md)

## Depends on

- task_083

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Create `cascade/comments/gate.py` with `GateResult{blocked, threads[{id,doc_id,section,blocking}], warnings}`, `is_section_thread(doc_id, section, *, root)` and `blocking_threads_for(work_id, *, root)`.

Load open blocking roots (parent null, state=open, blocking=true) from work_id, its parent feature (if task), and parent epic (dec_010). Affected set precedence (dec_003): (a) `blocks` non-empty -> exactly those ids (unknown ignored); (b) epic section thread (dec_008 heading match) -> epic + child features whose `cites` includes `{epic_id}#{section}`; (c) feature section thread or doc-level -> doc + all children. Tasks inherit from parent feature. Replies never carry scope. Unmatched cites (no current heading on cited doc) -> `warnings`, never block. Use `cascade.comments.section_slug` from feat_016; do not fork or import amendment/filename sluggers. Historical free-text sections are doc-level (D5). H1/general/unmatched => doc-level.

Tests: ONE table-driven test covering (a)/(b)/(c), task inherit, ancestor epic-section hitting a citing feature, non-citing feature not blocked, unmatched-cite warning, free-text historical section as doc-level. Do not duplicate per caller.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
