---
id: feat_018
title: Human resolve and audit
tier: feature
status: backlog
parent: epic_002
children: []
depends_on:
- feat_016
- feat_017
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-10-18'
updated: '2026-10-18'
---
# Human resolve and audit

## Parent Epic

[epic_002](../../epics/2_active/epic_002_plan_view_review_threads.md) — Plan-view review threads.

Depends on: [feat_016](feat_016_comment_read_api_and_war_room_wiring.md), [feat_017](feat_017_plan_viewer_comment_chrome.md).

Cites (promote to frontmatter `cites:` when feat_019 lands): `epic_002#intent`, `epic_002#cross-module-constraints`.

Constraints this feature must honor:

- Blocking and resolve are human-only (epic constraint + dec_002). Agents may reply; they may not resolve or set blocking.
- Resolved threads stay in `docs/_comments/{doc_id}.jsonl`. Do not delete or rewrite history other than flipping `state` to `resolved`.
- Completion rollup is unchanged: any **open human** thread still blocks epic/feature closeout (feat_008), whether or not it is blocking.
- Localhost only. No new store.

## Scope

**In**

- Add POST `/api/comment/resolve` `{doc_id, comment_id}` with author forced to `human`. 404 if missing; 400 if already resolved is fine (idempotent 202 is also fine — pick one and test it).
- Change `cascade.comments.store.resolve_comment` to require `author="human"`. Agent callers fail closed (`ResolveNotAllowed`).
- Unregister `resolve_comment` from epic and feature planning tool registries (or keep the name and always raise). Agents keep `reply_comment`.
- Plan viewer: a **Resolve** control on each open root thread (human page, no auth beyond localhost). Calls the new route, then reloads threads. Resolved threads stay listed, visually quieter (feat_017 `.resolved`).
- Optional audit: when an agent turn locks a choice in response to a thread, `record_decision` body includes `In reply to: cmt_NNN` (DESIGN §10.4 already shows this). No new linkage table, no new sidecar field.

**Out**

- Letting agents resolve after they patch the doc (today's implicit path). Human must click Resolve. That is the human gate.
- Dispatch / mint / merge gates (feat_019). Resolving is what unblocks those gates.
- Agent review playbook (feat_020) beyond the one-line `In reply to:` convention above.
- Soft-delete, hide-resolved toggle, or GitHub-style "outdated and resolved" auto-collapse.
- A force-unresolve. Re-open is a new root comment.

## Data structures

No new types. `Comment.state` remains `open | resolved`.

```text
ResolveNotAllowed   # store error when author != human
```

## API contracts

```text
POST /api/comment/resolve
     {doc_id, comment_id}
     -> 202 {ok, comment_id}
     author is always human
     emits CommentResolved (already in store)
     does not kick off an agent turn

resolve_comment(...)  # agent tool
     MUST fail for epic_manager / epic_architect / feature_lead / feature_architect
```

Existing `CommentResolved` queue event may still be ingested; it must not start a planning turn that then resolves other threads.

## Logic flow

```mermaid
flowchart TD
  H[Human Resolve click] --> API[POST /api/comment/resolve]
  API --> STORE[state=resolved in JSONL]
  STORE --> UI[thread shows resolved]
  AGENT[Agent resolve_comment] --> DENY[ResolveNotAllowed]
```

## Task breakdown

Feature Team mints after dispatch. Suggested slice:

1. **Store + tool guard** — `author=human` on resolve; agent tools denied. Store/API tests.
2. **HTTP resolve + plan button** — POST route; Resolve control on feat_017 thread list. One plan-viewer + API test.

`In reply to:` is a playbook line, not a third implementation task.

## Risks & upward questions

- Today's agent tools can resolve. Shipping feat_017 before this feature leaves a window where the UI has no button and agents still can. Dispatch feat_018 next to feat_017, or the same wave.
- Idempotent vs 400-on-already-resolved: prefer **idempotent 202** so a double click is not an error.
- Not kicking off a turn on resolve avoids an agent immediately re-opening debate. If the operator wants a closeout note, they type a reply first.

## Decision log

- **D1 — Agents cannot resolve, even after a doc patch.** The human gate in Intent is a click, not a convention. Matches "Mark a thread resolved only as human."
- **D2 — No turn on resolve.** Resolve is a gate release, not a new question.
- **D3 — Audit is `In reply to:` in the decision log.** DESIGN §10.4 already specifies it; a join table would be a second source of truth.
