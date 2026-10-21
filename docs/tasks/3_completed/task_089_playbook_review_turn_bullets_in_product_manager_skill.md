---
id: task_089
title: 'Playbook: review-turn bullets in product_manager skill'
tier: task
status: completed
parent: feat_020
children: []
depends_on:
- task_088
owners:
- swe
skills: []
parent_rev: d70923530f6ba4b71331445d66ecdfdb94c57572
created: '2026-10-20'
updated: '2026-10-20'
---
# Playbook: review-turn bullets in product_manager skill

## Parent Feature

[feat_020](../../features/2_active/feat_020.md)

## Depends on

- task_088

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Add a short review-turn section to the existing `skills/roles/product_manager/SKILL.md` (loaded by epic_manager and feature_lead). No new skill file or path (D3). Add a one-liner to `frugal_engineering` only if needed.

Five bullets:
1. Read the thread (`read_doc` + comments).
2. Answer, patch the owning spec, or `record_decision` (include `In reply to: cmt_NNN` when locking a choice).
3. `reply_comment` with what changed or why not.
4. If a feature turn needs an epic contract change: `propose_epic_amendment`; do not silently edit the epic.
5. Never `resolve_comment`.

Keep it brief; no tests needed beyond the task-1 system test. Depends on task 1 so the playbook describes the shipped behavior.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
