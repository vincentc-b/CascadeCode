---
id: epic_002
title: Plan-view review threads
tier: epic
status: active
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-18'
updated: '2026-10-18'
---

# Plan-view review threads

## Intent

Give the operator **GitHub-style review on the plan page**: select text or a section in **View plan**, start a thread, and have the **owning agent team** (Epic or Feature) respond — update the plan, answer the question, push back, or record a decision. Threads stay on the plan surface instead of only in War Room chat.

**Human gate:** a thread that touches open product decisions must be **resolved by a human** before work that would rely on those decisions proceeds. That includes minting tasks, dispatching features/tasks, and merges when the thread’s scope covers the affected doc sections or downstream children.

This epic extends the existing comment sidecar (`docs/_comments/{doc_id}.jsonl`, feat_005) and plan viewer (feat_012). It does **not** replace Epic chat or amendments; it is the async, plan-anchored path for “talk to the team about this paragraph.”

Operator success:

1. Open `/plan/epic_002` (or any epic/feature plan) and leave an inline or section-anchored comment without attaching to a live room.
2. See the Epic Team or Feature Team reply in-thread; optionally see the markdown body or decision log update after the agent turn.
3. Mark a thread **resolved** only as human; unresolved **blocking** threads visibly stop dispatch/merge for scoped work.
4. Use the same UX for epic plans (Epic Team owns) and feature plans (Feature Team owns).

## Macro-architecture

```
Plan viewer (GET /plan/{id})
  ├─ renders markdown body (existing)
  ├─ loads GET /api/comments/{doc_id}  [new read API]
  ├─ inline / section anchors + thread UI
  └─ POST /api/comment, reply, resolve   [extend existing routes]

docs/_comments/{doc_id}.jsonl          [unchanged store; richer anchor UX]
        │
        ▼ CommentPosted / CommentReplied
Epic graph or Feature graph (owning doc_id)
        │
        ├─ reply_comment / resolve_comment / write_doc / record_decision
        └─ optional: propose_epic_amendment when epic section changes

Watchdog deliver_queue_kickoffs → kickoff_turn (existing)

Dispatch law + new scope gates
  ├─ refuse dispatch_feature / dispatch_task / mint_task when blocking open threads scope hits
  └─ completion rollup unchanged: any open human thread still blocks closeout
```

**Owning team:** epic-tier `doc_id` → graph `epic_{id}`; feature-tier `doc_id` → graph `feat_{id}`. Task plans are read-only for comments in v1 (tasks have no room; operator comments on parent feature or epic).

## Cross-module constraints

- **Filesystem is truth.** Comments remain sidecars, not inline in the `.md` body (feat_005 / DESIGN §10.3).
- **Localhost only.** Plan viewer and APIs stay on `127.0.0.1`; no GitHub OAuth or remote PR comments.
- **Dispatch law unchanged:** Epic activate = human only; feature/task dispatch = human or Boss. Agents still cannot dispatch themselves.
- **Kickoff edges only:** Posting a comment enqueues `CommentPosted`; one agent turn is delivered by the watchdog — no timer polling for “new comments on main.”
- **Stacked worktrees:** Comment sidecars for an active epic/feature live in the same git root as that team’s plan (`resolve_doc_worktree` / existing comment repo rules).
- **Read-only plan renderer** may gain comment *chrome*; plan body edits still go through agent tools or git, not WYSIWYG in the viewer (feat_012 read-only stance unless explicitly extended).
- **Blocking is human-only** on create (existing store rule). Agents may reply but not resolve or set blocking.
- **Scope:** v1 may treat “affected work” as: (a) the commented `doc_id`, (b) explicit `section` heading, and (c) optional `blocks: [work_id, …]` on the root comment — exact schema is for the Epic Team to lock in feat specs.

## Core dependencies

- feat_005 comment sidecar + `CommentPosted` queue delivery
- feat_012 plan viewer (`GET /plan/{id}`, `/api/doc/{id}`)
- feat_004 / feat_005 epic & feature `reply_comment`, `resolve_comment`, graph boot
- feat_014 workspace / worktree doc resolution for reads
- War Room `POST /api/comment` (already persists; War Room UI stub text is stale)

## Feature breakdown

Epic Team should mint these into `docs/features/1_backlog/` (ids assigned at mint time):

1. **Plan viewer comment chrome** — Thread list and anchors on `/plan/{id}`; text selection → `section` + optional `anchor` snippet; human resolve control; load threads via read API; link “Back to War Room” unchanged.

2. **Comment read API & War Room wiring** — `GET /api/comments/{doc_id}`; replace War Room comment stub with real compose (or deep-link to plan view). Toasts on new human comments when not attached (existing behavior).

3. **Agent review turns** — Ensure `CommentPosted` / `CommentReplied` reliably trigger one planning turn for the owning graph; playbook: interpret thread, update doc or decision log, reply in sidecar; escalate to amendment when epic contract changes.

4. **Scoped dispatch gates** — Extend dispatch law and `mint_task` so **open blocking** threads with scope prevent:
   - `dispatch_feature` / `dispatch_task` on affected features/tasks
   - `mint_task` on affected features (already blocks on any blocking comment on feature — tighten to scope if `blocks` list present)
   - Human-visible refusal reasons in War Room dispatch responses

5. **Human resolve & audit** — Only human may `resolve_comment`; resolved threads remain in JSONL; plan UI shows open vs resolved; optional `record_decision` linkage when a thread locks a choice.

## Open questions

- **Anchor model:** GitHub uses line-level threads; v1 may use section heading + optional quoted substring (`anchor` field exists). Is line-level required for MVP?
- **Default blocking:** Should every human plan comment default to `blocking: true` until resolved, or opt-in checkbox (DESIGN today is opt-in)?
- **Cross-doc scope:** If I comment on epic § Memory layout, do we block dispatch of all features under that epic, or only features whose specs cite that section?
- **Boss dispatch:** When Boss auto-dispatches, same scope gates apply — confirm no bypass.
- **Pointer epics on trunk:** Comments on trunk pointer body vs live epic worktree — resolve reads/writes to epic worktree spec (feat_014).

## Decision log

_(none — human brief 2026-10-18)_

## Amendment log

_(none)_
