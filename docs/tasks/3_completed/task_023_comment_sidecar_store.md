---
id: task_023
title: Comment sidecar store and epic/feature thread tools
tier: task
status: completed
parent: feat_005
children: []
depends_on:
  - task_018
  - task_019
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Comment sidecar store and epic/feature thread tools

## Parent Feature

[feat_005](../../features/3_completed/feat_005_feature_team.md) — Feature Team, comments, and drop-in.

## Depends on

- task_018 — queue ingest for `CommentPosted` / replies / resolves
- task_019 — path rules for `docs/_comments/{doc_id}.jsonl`

## Acceptance criteria

- Shared store under `cascade/comments/` (e.g. `store.py`, `types.py`) persisting JSONL at `docs/_comments/{doc_id}.jsonl` with the **Comment** schema from feat_005 (`id` `cmt_NNN`, `doc_id`, `section`, `anchor`, `author`, `body`, `parent`, `state`, `blocking`, `created` ISO-8601).
- `comment(doc_id, section, body, anchor=null, blocking=false, *, author, root) -> comment_id`:
  - `blocking=true` allowed only when `author=human`; feature/epic agent authors cannot set blocking (raise on violation).
  - Append-only sidecar; enqueue `CommentPosted` to the **owning** graph only (feature doc → feature id queue; epic doc → epic id queue).
  - If human is not attached to that graph’s war-room/feature room, enqueue a `Toast` on `war_room` with kind `comment` (use existing toast/event patterns).
- `reply_comment` / `resolve_comment` for **feature** tools: owning feature team only; cannot resolve epic-owned threads (`doc_id` tier epic → `FeatureToolDenied`).
- Replace `cascade/epic/stubs.py` implementations for `reply_comment` and `resolve_comment` so epic threads use the same store; epic tools only when `doc_id` is the active epic. Leave `resolve_amendment` as **501** referencing feat_006.
- Human-facing HTTP route (e.g. `POST /api/comment`) or documented workspace entrypoint that calls `comment` with `author=human`, optional `blocking`, without requiring attach.
- `tests/comments/test_store.py` and `tests/feature/test_comments.py` cover schema, blocking rules, queue dest, toast when detached, epic vs feature ownership, and stub replacement (no 501 on reply for epic when store wired).

## Files likely touched

- `cascade/comments/store.py`
- `cascade/comments/types.py`
- `cascade/feature/comments_tool.py` (register feature reply/resolve/comment if exposed to graph)
- `cascade/epic/stubs.py` (real reply/resolve for epic)
- `cascade/war_room/` (comment POST route if not elsewhere)
- `tests/comments/test_store.py`
- `tests/feature/test_comments.py`
- `tests/epic/test_stubs.py` (update expectations for reply/resolve)

## Implementation notes

Monotonic `cmt_NNN` per sidecar file. Resolved threads set `state=resolved`. Feature graph tools register via `load_feature_tools` import side (task_024). Do not implement amendment sidecars or `AmendmentProposed` (feat_006). Agents calling `comment` with `blocking=True` is a test-required failure.

## Skills

_(none)_

## Test plan

- `python3 -m pytest tests/comments/test_store.py tests/feature/test_comments.py tests/epic/test_stubs.py -q`

## Out of scope

- `propose_epic_amendment` implementation (task_025 stub only)
- Briefing pack open_comments assembly (task_024)
- `mint_task` blocking integration tests live in task_021 but may import store helper from here
