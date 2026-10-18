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
- Kickoff edges only: posting or replying enqueues `CommentPosted` / `CommentReplied`. Do not add timer polling. Keep today's `kickoff_graph_queue_event` call; feat_020 replaces delivery (dec_011). Do not add a second helper here.
- Section is never empty on a root (dec_008). Doc-level vs section-thread is a *heading match*, not a missing field.

## Scope

**In**

- Treat GET `/api/comments/{doc_id}` as the locked read API. Keep the current 404 (unknown id) and 400 (task-tier) behavior. Return the new optional fields below; older sidecar rows omit them and deserialize as null / empty.
- Extend `cascade.comments.types.Comment` and POST `/api/comment` so a root comment may store `line_start`, `line_end`, `doc_sha`, and `blocks` (`list[work_id]`, default empty). `section` and `anchor` stay required/optional as today. `section` is stored as the shared slug (see `section_slug()`), not the raw heading text.
- Extend `cascade.comments.store.comment()` with the same optional kwargs. `Comment` is frozen: every constructor (`_append_comment`, `resolve_comment` rewrite, tests) must copy the new fields. `from_dict` treats missing keys as `None` / `[]`. `to_dict` always emits them.
- When POST `/api/comment` includes `parent`, treat it as a human in-thread reply: call existing `reply_comment` (emits `CommentReplied`). `section` / `anchor` / `blocking` / `line_*` / `doc_sha` / `blocks` are optional and **ignored**; inherit `section` and `anchor` from the parent. 404 if parent is missing. Do not add a second reply URL.
- Add `section_slug(heading: str) -> str` as `cascade.comments.section_slug` (one function in `cascade/comments/`). **Do not** reuse `cascade.board.paths.slugify` or `cascade.amendments.store.section_slug` — those use underscores for filenames. This function is hyphenated GitHub-style. Viewer (feat_017) and gate (feat_019) import it.
- War Room: point the existing **View plan** control at `/plan/{id}#plan-comments` for epic and feature rows only. No second compose form and no extra Comments button. Toasts on new human comments when not attached stay as they are.
- POST `/api/comment` keeps the existing `kickoff_graph_queue_event` call so one owning-graph turn is requested for both roots and replies until feat_020 lands.

**Out**

- Line-level gutter, text-selection, re-anchor, and outdated chrome (feat_017).
- Resolve HTTP, human-only resolve enforcement, thread-level cascade, and `record_decision` linkage (feat_018).
- Dispatch / mint / merge gates and `cites:` frontmatter on `WorkMeta` (feat_019).
- Agent playbook and watchdog-only comment kickoff (feat_020).
- GitHub OAuth, remote PR comments, or a new comment database.
- A new `/api/comment/reply` route.
- Validating `blocks` ids against the board (gate ignores unknown ids).
- Changing `CommentPosted` payload shape beyond adding the new optional keys already stored on the record.
- Rewriting historical sidecar `section` strings to slugs.

## Data structures

```text
Comment  # extends feat_005; new fields optional for back-compat
  id: "cmt_NNN"
  doc_id: WorkId
  section: str                 # section_slug(nearest heading); never empty on a root
  anchor: str | null           # quoted snippet
  line_start: int | null       # 1-based source line; null = no line bind
  line_end: int | null         # >= line_start when both set
  doc_sha: str | null          # spec blob sha at post time
  blocks: [WorkId]             # explicit scope override; empty = use dec_003 later
  author: human | feature_lead | feature_architect | epic_manager | epic_architect
  body: str
  parent: comment_id | null
  state: open | resolved
  blocking: bool               # default false; human-only to set true
  created: datetime
```

`section_slug(heading)`: trim, lowercase, whitespace (and other non `[a-z0-9]`) to `-`, drop characters outside `[a-z0-9-]`, collapse repeats, strip leading/trailing `-`. `# Memory layout` → `memory-layout`. Empty heading is invalid (store already refuses empty `section`).

**Section vs doc-level (dec_008):** a root is a *section thread* iff `section` equals `section_slug(h)` for some current `##` or deeper heading on that doc. Otherwise it is *doc-level* (H1 title slug, `general`, or unmatched). The store does not store a separate scope flag.

## API contracts

```text
GET  /api/comments/{doc_id}
     -> {doc_id, comments: [Comment]}
     404 unknown id; 400 task-tier (unchanged)

POST /api/comment
     {doc_id, body,
      section?, anchor?, blocking?=false,
      line_start?, line_end?, doc_sha?, blocks?, parent?}
     -> 202 {ok, comment_id, kickoff}
     author is always human on this route
     parent omitted: root comment; `section` required; blocking=true allowed
     parent set: reply via store.reply_comment; section/anchor/blocking/line/sha/blocks ignored
     section is slugified before persist on roots (client may send heading or slug)
     404 if parent is set and missing
     400 if root and section empty, or line_end < line_start
```

All binds: `127.0.0.1`. Sidecar path is the owning worktree via `resolve_doc_worktree`.

## Logic flow

```mermaid
flowchart LR
  WR[War Room View plan] -->|"/plan/id#plan-comments"| PV[Plan viewer]
  PV --> GET[GET /api/comments/id]
  PV --> POST[POST /api/comment]
  POST --> STORE["docs/_comments/id.jsonl in worktree"]
  STORE --> Q[CommentPosted or CommentReplied]
  Q --> KO[kickoff_graph_queue_event until feat_020]
```

## Task breakdown

Feature Team mints after dispatch. Suggested slice:

1. **Comment schema + `section_slug()`** — optional fields on `Comment` / store / `from_dict` back-compat; every `Comment(...)` constructor updated; store tests for old lines without the new keys; unit vector for `section_slug` (shared with feat_017 JS).
2. **POST field pass-through + parent-as-reply** — extend `_handle_comment`; section optional when `parent` set; keep kickoff + toast. API tests on the existing War Room server fixture.
3. **War Room deep-link** — View plan on epic/feature rows goes to `/plan/{id}#plan-comments`.

## Risks & upward questions

- `cites:` frontmatter is not on `WorkMeta` yet. This spec records cites in the body until feat_019 adds the field. Accepted limitation from dec_003.
- Slugifying `section` on write changes the stored string versus today's free-text headings (`"Open questions"` vs `open-questions`). Old rows stay as stored; the gate treats unmatched headings as doc-level (dec_008) and unmatched `cites:` as warnings (feat_019). Do not rewrite historical sidecars.
- Resolve stays off this feature so feat_018 can make it human-only without a race against agent tools.
- `cascade.amendments.store.section_slug` already exists and uses `_`. Importing the wrong function is a defect; tests should fail if comments slug with underscores.

## Decision log

- **D1 — No second compose surface.** War Room reuses View plan + `#plan-comments`. A board-side compose form would duplicate the plan viewer and rot again.
- **D2 — Replies use `parent` on POST `/api/comment`.** Extends the existing route; no `/api/comment/reply`. Section is optional on replies and inherited.
- **D3 — `cascade.comments.section_slug()` is the only slugger for comments/cites.** Viewer (feat_017) and gate (feat_019) import it. Filename/amendment sluggers stay separate.
- **D4 — Kickoff helper is feat_020.** This feature keeps the existing `kickoff_graph_queue_event` call so HTTP still requests a turn. Replacing it here would race feat_020.
