---
id: task_088
title: Shared human-comment kickoff via watchdog (HTTP enqueue-only)
tier: task
status: completed
parent: feat_020
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: d70923530f6ba4b71331445d66ecdfdb94c57572
created: '2026-10-20'
updated: '2026-10-20'
---
# Shared human-comment kickoff via watchdog (HTTP enqueue-only)

## Parent Feature

[feat_020](../../features/2_active/feat_020.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Implement `kickoff_human_comment(doc_id, comment_id, *, root) -> bool` and wire it into `deliver_queue_kickoffs`.

- Human CommentPosted/CommentReplied on an active (2_active) owning graph -> `kickoff_turn(kind="comment")` with `message` as dict `{"role": "human", "content": "cmt_NNN on {doc_id} #{section} [blocking]\n{body}"}`; cap content ~2k chars and tell the agent to read the sidecar for the rest. Must work with empty chat history (D1, D4).
- No-op for agent authors and CommentResolved: advance queue offset only, no turn (D2, D5).
- Comment events (human or agent) and CommentResolved must not fall back to the `queue_event` path; non-comment events (amendments, decisions) keep existing `queue_event` behavior.
- HTTP `_handle_comment` stays enqueue-only: if it calls `kickoff_graph_queue_event`, remove it (D5, D6). No HTTP eager turn.
- Human comment on a busy graph with an inflight turn must not be dropped; queue as next kind=comment per existing inflight rules.
- No new queue event types, no polling of /api/comments, no new persistence.

Acceptance (one system test): human comment on activated epic with empty chat -> exactly one kickoff; agent reply in thread -> no second kickoff; human resolve -> no kickoff; HTTP POST + subsequent watchdog tick -> exactly one kickoff.

Owning graph only: epic doc_id -> epic_{id}; feature doc_id -> feat_{id}. Tasks have no comment room.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
