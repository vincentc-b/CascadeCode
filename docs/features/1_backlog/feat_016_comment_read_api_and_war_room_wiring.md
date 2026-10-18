---
id: feat_016
title: Comment read API and War Room wiring
tier: feature
status: backlog
parent: epic_002
children: []
depends_on: []
owners:
- feature_lead
- feature_architect
skills: []
parent_rev: null
created: '2026-10-18'
updated: '2026-10-18'
---
# Comment read API and War Room wiring

## Parent Epic

[epic_002](../../epics/2_active/epic_002_plan_view_review_threads.md) — Plan-view review threads.

Cites (promote to frontmatter `cites:` when feat_019 lands): `epic_002#macro-architecture`, `epic_002#core-dependencies`, `epic_002#cross-module-constraints`.

Constraints this feature must honor:

- Filesystem is truth. Comments stay in `docs/_comments/{doc_id}.jsonl` (feat_005 / DESIGN §10.3). Do not write into the plan `.md` body.
- Localhost only. Routes stay on `127.0.0.1`.
- Pointer epics (dec_005): all comment reads/writes resolve through `resolve_doc_worktree` (already in `cascade.comments.store`). Trunk pointers never get their own sidecar.
- Existing GET `/api/comments/{doc_id}` and POST `/api/comment` already persist and toast. This feature extends them; it does not add a second store or a second read API.
- Blocking remains human-only on create, default `false` (dec_002). Agents still cannot set it.
- Kickoff edges only: posting or replying enqueues `CommentPosted` / `CommentReplied`. Do not add timer polling.

## Scope

**In**

- Treat GET `/api/comments/{doc_id}` as the locked read API. Keep the current 404 (unknown id) and 400 (task-tier) behavior. Return the new optional fields below; older sidecar rows omit them and deserialize as null / empty.
- Extend `cascade.comments.types.Comment` and POST `/api/comment` so a root comment may store `line_start`, `line_end`, `doc_sha`, and `blocks` (`list[work_id]`, default empty). `section` and `anchor` stay required/optional as today. `section` is stored as the shared slug (see `section_slug()`), not the raw heading text.
- Add POST `/api/comment/reply` `{doc_id, comment_id, body}` as a human-authored in-thread reply. Reuse `reply_comment` in the store (already emits `CommentReplied`). Do not allow `blocking` or new anchors on replies.
- Add `section_slug(heading: str) -> str` in `cascade/comments/` (one function, imported by the plan viewer and the dispatch gate). Heading rename that breaks a `cites:` entry is reported later by feat_019, not here.
- War Room: on each visible epic/feature row, add a **Comments** (or reuse **View plan**) deep-link to `/plan/{id}#plan-comments`. Do **not** build a second compose form on the board. Toasts on new human comments when not attached stay as they are.
- POST `/api/comment` and `/api/comment/reply` keep the existing `kickoff_graph_queue_event` call so one owning-graph turn is requested.

**Out**

- Line-level gutter, text-selection, re-anchor, and outdated chrome (feat_017).
- Resolve HTTP, human-only resolve enforcement, and `record_decision` linkage (feat_018).
- Dispatch / mint / merge gates and `cites:` frontmatter on `WorkMeta` (feat_019).
- Agent playbook for review turns (feat_020).
- GitHub OAuth, remote PR comments, or a new comment database.
- Changing `CommentPosted` payload shape beyond adding the new optional keys already stored on the record.

## Data structures

```text
Comment  # extends feat_005; new fields optional for back-compat
  id: "cmt_NNN"
  doc_id: WorkId
  section: str                 # section_slug(nearest heading); never empty on create
  anchor: str | null           # quoted snippet
  line_start: int | null       # 1-based source line; null = section/doc-level
  line_end: int | null
  doc_sha: str | null          # spec blob sha at post time
  blocks: [WorkId]             # explicit scope override; empty = use D3 rules later
  author: human | feature_lead | feature_architect | epic_manager | epic_architect
  body: str
  parent: comment_id | null
  state: open | resolved
  blocking: bool               # default false; human-only to set true
  created: datetime
```

`section_slug(heading)`: trim, lowercase, whitespace to `-`, drop characters outside `[a-z0-9-]`, collapse repeats. `# Memory layout` → `memory-layout`. Empty heading is invalid (store already refuses empty `section`).

## API contracts

```text
GET  /api/comments/{doc_id}
     -> {doc_id, comments: [Comment]}
     404 unknown id; 400 task-tier (unchanged)

POST /api/comment
     {doc_id, section, body, anchor?, blocking?=false,
      line_start?, line_end?, doc_sha?, blocks?}
     -> 202 {ok, comment_id, kickoff}
     author is always human on this route
     blocking=true allowed (human-only path)
     section is slugified before persist if the client sent a heading

POST /api/comment/reply
     {doc_id, comment_id, body}
     -> 202 {ok, comment_id, kickoff}
     author is always human; blocking ignored
     404 if parent missing
```

All binds: `127.0.0.1`. Sidecar path is the owning worktree via `resolve_doc_worktree`.

## Logic flow

```mermaid
flowchart LR
  WR[War Room row] -->|deep-link| PV["/plan/id#plan-comments"]
  PV --> GET[GET /api/comments/id]
  PV --> POST[POST /api/comment or /reply]
  POST --> STORE["docs/_comments/id.jsonl in worktree"]
  STORE --> Q[CommentPosted or CommentReplied]
  Q --> KO[kickoff_graph_queue_event]
```

## Task breakdown

Feature Team mints after dispatch. Suggested slice:

1. **Comment schema + `section_slug()`** — optional fields on `Comment` / store / `from_dict` back-compat; unit-of-store tests for old lines without the new keys.
2. **HTTP reply + POST field pass-through** — extend `_handle_comment`; add `/api/comment/reply`; keep kickoff + toast. API tests on the existing War Room server fixture.
3. **War Room deep-link** — epic/feature row link to `/plan/{id}#plan-comments`. No new compose pane.

## Risks & upward questions

- `cites:` frontmatter is not on `WorkMeta` yet. This spec records cites in the body until feat_019 adds the field. Accepted limitation from dec_003.
- Slugifying `section` on write changes the stored string versus today's free-text headings (`"Open questions"` vs `open-questions`). Old rows stay as stored; the gate treats them as unmatched cites and warns (feat_019). Do not rewrite historical sidecars.
- Resolve stays off this feature so feat_018 can make it human-only without a race against agent tools.

## Decision log

_(entries via record_decision)_
