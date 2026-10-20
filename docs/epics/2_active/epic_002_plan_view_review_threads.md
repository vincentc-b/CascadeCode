---
id: epic_002
title: Plan-view review threads
tier: epic
status: active
parent: null
children:
- feat_016
- feat_017
- feat_018
- feat_019
- feat_020
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-18'
updated: '2026-10-20'
provider: cursor
models:
  epic_manager: grok-4.6
  epic_architect: grok-4.6
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
  ├─ loads GET /api/comments/{doc_id}  [feat_016 shipped]
  ├─ inline / section anchors + thread UI  [feat_017 shipped]
  └─ POST /api/comment (root or parent reply); POST /api/comment/resolve  [feat_018 shipped]

docs/_comments/{doc_id}.jsonl          [unchanged store; richer anchor fields]
        │
        ▼ CommentPosted / CommentReplied
Epic graph or Feature graph (owning doc_id)
        │
        ├─ reply_comment / write_doc / record_decision
        ├─ resolve is human-only, thread-level (feat_018 shipped); agents do not get the tool
        └─ optional: propose_epic_amendment when epic section changes

Watchdog deliver_queue_kickoffs → kickoff_turn(kind="comment") for human authors (feat_020 planning)
  HTTP POST enqueues only; skipped events still ingest the queue offset (dec_021–dec_025)
  Graph boots like War Room attach into resolve_doc_worktree — never trunk (dec_023)
  In-thread reply_comment on the triggering comment is required; spec edit is not a substitute (dec_024)
  Watchdog/kickoff never write the sidecar; reply is the existing agent tool (dec_025)

Dispatch law + new scope gates (feat_019 shipped, task_083–085)
  ├─ cascade.comments.blocking_threads_for live-loads work+ancestors; refuse dispatch/mint_task/merge
  └─ completion rollup unchanged: any open human thread still blocks closeout
  Agent resolve_comment is unregistered (feat_018 shipped; dec_013 leak closed)
```

**Owning team:** epic-tier `doc_id` → graph `epic_{id}`; feature-tier `doc_id` → graph `feat_{id}`. Task plans are read-only for comments in v1 (tasks have no room; operator comments on parent feature or epic).

## Cross-module constraints

- **Filesystem is truth.** Comments remain sidecars, not inline in the `.md` body (feat_005 / DESIGN §10.3).
- **Localhost only.** Plan viewer and APIs stay on `127.0.0.1`; no GitHub OAuth or remote PR comments.
- **Dispatch law unchanged:** Epic activate = human only; feature/task dispatch = human or Boss. Agents still cannot dispatch themselves.
- **Kickoff edges only:** Posting a comment enqueues `CommentPosted`; one agent turn is delivered by the watchdog — no timer polling for “new comments on main.” HTTP POST does not start a turn (dec_011, dec_012, dec_021–dec_025). Resolve POST also does not start a turn (dec_011, dec_020). Do not add HTTP `kickoff_graph_queue_event` to “fix” cold start. Filter lives inside existing `deliver_queue_kickoffs`; skipped events still advance the offset (dec_023). `kickoff_turn` returns like live chat — do not wait for `reply_comment` (dec_025).
- **Stacked worktrees:** Comment sidecars for an active epic/feature live in the same git root as that team’s plan (`resolve_doc_worktree` / existing comment repo rules). A comment `kickoff_turn` uses that same worktree as the graph workspace (dec_005, dec_023); trunk pointers never get a sidecar.
- **Read-only plan renderer** may gain comment *chrome*; plan body edits still go through agent tools or git, not WYSIWYG in the viewer (feat_012 read-only stance unless explicitly extended).
- **Comment chrome is render-only (dec_016).** `line_start` / `line_end` are 1-based markdown source lines from the renderer token source map. Re-anchor and outdated never rewrite the sidecar. `#plan-comments` is upserted by `data-comment-id`, never replaced via `innerHTML`. Task-tier GET `/api/comments` 400 stays. **feat_017 shipped this** (task_080–082). **feat_018 shipped the Resolve button** on that list; do not add a second panel.
- **Blocking is human-only** on create (existing store rule). Agents may reply but not resolve or set blocking. feat_018 shipped the store+tool guard and the Resolve button; `resolve_comment` is unregistered. The dec_013 leak is closed. feat_020 must not re-register the tool.
- **Comment turns are watchdog-only (dec_011, dec_012, dec_021–dec_025).** Filter lives inside existing `deliver_queue_kickoffs` (not a second subscriber). It starts `kickoff_turn(kind="comment")` only for human `CommentPosted` / `CommentReplied`. Agent replies and `CommentResolved` ingest the queue offset and do not start a turn; skipped events must still advance the cursor. Offset is exactly-once — no `kicked_off` sidecar flag. One turn per matching event, owning graph only (`epic_{id}` / `feat_{id}` from `doc_id`); do not fan-out to parent epic, child features, or iterate owners/roles. Empty or never-attached graphs still boot **the same way War Room attach does**: same roster/skills/tools (`resolve_comment` stays unregistered; existing `reply_comment` stays registered), workspace `resolve_doc_worktree(doc_id)` — never trunk, never a throwaway worktree, never a headless comment runner. `kind="comment"` is a KickoffReason tag only; the turn path is the existing planning turn (same speaker selection as live chat). Author filter is the event/sidecar `author` field (`human` only). `KickoffReason.message` is `{role: "human", content: ...}` with the dec_025 prefix. Playbook is one short section on the existing `product_manager` skill (loaded by that boot, not injected as a system prompt, not copied onto architect skills). Always `reply_comment` in-thread with the existing tool `comment_id` = the triggering comment id (dec_024, dec_025); a spec/decision edit is not a substitute. `write_doc` remains optional. No comment-failure toast/spinner. No HTTP eager turn, no generic `queue_event` kickoff, no comment-only role, no digest/batch, no second writer, no poll/spinner for the agent reply. If `kickoff_turn` raises, keep the event (existing watchdog retry).
- **Comment reply write-path (dec_025).** `deliver_queue_kickoffs` and `kickoff_turn` never call `reply_comment` and never append the sidecar (no auto-ack). The in-thread reply is only the existing feat_004/005 `reply_comment(comment_id, body)` tool during the existing planning turn — `comment_id` is the parent (the triggering event’s comment id, not the thread root and not the human row’s parent). Do not add a `parent` kwarg, a `review_comment` facade, or a second reply tool. Agents never POST `/api/comment` (that route is always `author=human` and would loop). Stored author is the speaking role already in the feat_016 enum (`epic_manager` / `feature_lead` / …), never `human`, never a new `comment-reviewer`. `KickoffReason.message.content` is the only channel the model sees: four-line prefix `comment_id` / `section` / `blocking` / optional `parent:` (omit the line when the human row is a root) then a blank line then the human body verbatim — no extra KickoffReason fields, no sidecar dump (`line_*`, `doc_sha`, `blocks`, siblings). `kickoff_turn` returns like live chat; offset advances when kickoff is accepted, not when a sidecar reply appears. Do not skip a turn because the thread was resolved before the agent spoke; do not un-resolve. Restore the existing `reply_comment` registration if missing; do not add a `kind="comment"` allowlist.
- **Gate is store-only and shipped (dec_017, dec_018, dec_019).** `cascade.comments.blocking_threads_for(work_id)` is a pure function next to the comment store. Each call live-loads open blocking roots from the work and ancestors via sidecar + `resolve_doc_worktree` (never trunk pointers, never a boot-time cache, never plan-viewer JS). It reads current worktree `##+` headings. It does not consult outdated state, line numbers, or rewrite comments. Replaced the existing `mint_task` any-blocking check; do not stack it back. Do not gate `mint_feature` or `activate_epic`. Closeout rollup stays separate. Merge means the existing feature/task integration merge for that `work_id`, not git commit. Do not re-implement the gate in feat_020.
- **Scope (locked, see dec_003/dec_004/dec_008/dec_010/dec_018):** affected work for an open blocking *root* thread, in order of precedence:
  (a) explicit `blocks: [work_id, …]` on the root comment, if **non-empty**: exclusive membership of those ids plus tasks of any listed feature (unknown ids ignored). Do not also apply (b) or (c);
  (b) else, *section thread* on an **epic**: the epic plus only child features whose frontmatter `cites:` includes `{epic_id}#{section_slug}`;
  (c) else, *section thread* on a **feature**, or any *doc-level* thread: the commented doc and all its children.
  A root is a section thread iff stored `section` **as-is** equals `section_slug(h)` for some current `##` or deeper heading on that doc; otherwise it is doc-level (H1, `general`, unmatched, historical free-text). Do not re-slugify stored section on read. Section is never empty.
  Tasks inherit blocking from their parent feature. `blocking_threads_for(work_id)` loads roots from the work **and its ancestors** (parent feature, parent epic). Slugs come from one shared `cascade.comments.section_slug` (feat_016, dec_006). `WorkMeta.cites` is feature-tier only. epic_002 children still record cites in spec body, not frontmatter (dec_019 known limitation).

## Core dependencies

- feat_005 comment sidecar + `CommentPosted` queue delivery
- feat_012 plan viewer (`GET /plan/{id}`, `/api/doc/{id}`)
- feat_004 / feat_005 epic & feature `reply_comment`, graph boot
- feat_014 workspace / worktree doc resolution for reads
- feat_016 comment fields, parent-as-reply, `section_slug()`, View plan `#plan-comments` (completed 2026-10-20). HTTP kickoff is feat_020 (dec_012, dec_021).
- feat_017 plan-viewer comment chrome (completed 2026-10-20). Gate must not consult chrome outdated state (dec_017).
- feat_018 human resolve and audit (completed 2026-10-20). Agent `resolve_comment` is unregistered; the dec_013 leak is closed.
- feat_019 scoped dispatch gates (completed 2026-10-20; task_083–085). Do not reopen the gate.
- War Room `POST /api/comment` and `GET /api/comments/{doc_id}` (persist; board compose is a deep-link, feat_016)

## Feature breakdown

feat_016, feat_017, feat_018, and feat_019 are complete. **feat_020 is in planning** (dec_021, dec_022, dec_023, dec_024, dec_025). I have not minted tasks.

1. **[feat_016](../../features/3_completed/feat_016_comment_read_api_and_war_room_wiring.md) — Comment read API and War Room wiring** *(completed 2026-10-20; task_077–079 merged)* — GET `/api/comments/{doc_id}` and POST `/api/comment` carry `line_start` / `line_end` / `doc_sha` / `blocks`; `parent` is a reply (section inherited); `cascade.comments.section_slug()` is hyphenated GitHub-style. View plan deep-links to `/plan/{id}#plan-comments`. No second compose form. HTTP `kickoff_graph_queue_event` was **not** added (feat_016 D5 / dec_012); feat_020 owns delivery. Merge must keep one GET `/api/comments` handler. feat_016’s API table still shows a `kickoff` key; **that row is stale** — shipped POST is `202 {ok, comment_id}`.

2. **[feat_017](../../features/3_completed/feat_017_plan_viewer_comment_chrome.md) — Plan viewer comment chrome** *(completed 2026-10-20; task_080–082 merged)* — GitHub-style line threads on `/plan/{id}`: `data-src-line` from markdown source maps, gutter/selection compose, `parent` reply, render-only re-anchor / outdated, `#plan-comments [data-comment-id]` on each root. Blocking checkbox default off. Dropped the 3s poll. Resolve **status** only — the button is feat_018 (dec_007, shipped). POST 202 `{ok, comment_id}` — reload GET; no kickoff wait (dec_012, dec_015, dec_016). Gate (feat_019 shipped) must not read chrome outdated flags (dec_017).

3. **[feat_020](../../features/2_active/feat_020_agent_review_turns.md) — Agent review turns** *(planning 2026-10-20)* — One `kickoff_turn(kind="comment")` per human CommentPosted / CommentReplied, including graphs with no prior chat. Watchdog delivers; HTTP enqueues only (do not add an HTTP eager turn — dec_012, dec_021–dec_025). Agent replies and `CommentResolved` do not loop. Playbook on existing `product_manager` skill.

   **Architect lock (dec_021) — Feature Team honors this when minting. Do not reopen epic decisions.**
   - Watchdog `deliver_queue_kickoffs` is the only path that starts a turn: event in `{CommentPosted, CommentReplied}` AND `author=human`. Agent `CommentReplied`, `CommentResolved`, and every other event ingest the queue offset and do not start a turn.
   - One `kickoff_turn(kind="comment")` per matching event, on the owning graph only (`epic_{id}` / `feat_{id}` from `doc_id`). Task-tier comments stay 400 — no task graph turn and no parent-fanout.
   - `KickoffReason.message` is `{role: "human", content: ...}` — content is the human body plus `comment_id`, `section`, `blocking`, and `parent` if reply. Not a system prompt and not the whole sidecar.
   - Empty or never-attached graphs must still run: `kickoff_turn` boots the owning graph if needed. Do not require War Room attach. Do not add HTTP `kickoff_graph_queue_event` to “fix” cold start; if that call exists on POST `/api/comment`, delete it.
   - Playbook is a short section on the existing `product_manager` skill; the owning graph’s existing turn loop runs. Do not add a comment-only role or a second graph.
   - Agent may `reply_comment` and optionally `write_doc` / `record_decision`; `propose_epic_amendment` only when an epic contract section would change. Never resolve, never set blocking, never dispatch, never call `blocking_threads_for`, never re-register `resolve_comment`.
   - Agent `reply_comment` uses the existing sidecar via `resolve_doc_worktree`. No second writer, no poll, no chrome change, no new queue topic, no timer, no digest/batch, no sidecar rewrite of line/section/doc_sha.
   - **Out:** Resolve button (feat_018 shipped), gates (feat_019 shipped), second War Room compose, `force` flag, cites backfill.
   - Suggested slice: (1) watchdog filter + `kickoff_turn` including empty-chat + message shape; strip HTTP eager kickoff if present; (2) playbook paragraph on existing PM skill. High-signal test: human POST → one turn on the owning graph including a never-chatted graph; agent reply does not start a second turn; resolve does not start a turn; HTTP 202 has no `kickoff` key; wrong graph is not booted. Not a mock of `section_slug` or the gate.

   **Product lock (dec_022) — Feature Team honors this when minting. Do not reopen epic decisions.**
   - Operator success #2 is a human comment on an epic or feature plan → one owning-team turn; an in-thread reply may show on the next GET / plan reload. Not a spinner, poll, websocket, or second War Room compose.
   - Playbook is one short section on the existing `product_manager` skill (already used by epic_manager and feature_lead). Do not add a skill file, a comment-only role, or a second graph. Do not inject the playbook as a KickoffReason system prompt.
   - A `reply_comment` that answers the question meets the bar. `write_doc` / `record_decision` are optional. `propose_epic_amendment` only when an epic contract section would change.
   - Never resolve, never set blocking, never dispatch, never call `blocking_threads_for`, never re-register `resolve_comment`.
   - POST `/api/comment` stays `202 {ok, comment_id}` with no `kickoff` key. Delete `kickoff_graph_queue_event` on that route if present. Watchdog is the only turn starter (dec_021).
   - One turn per human `CommentPosted` / `CommentReplied` on the owning graph only. Empty/never-attached graphs boot. Task-tier stays 400. Do not fan-out to the parent epic or child features.
   - Agent replies and `CommentResolved` do not start a turn.
   - **Out:** chrome (feat_017 shipped), Resolve button (feat_018 shipped), gates (feat_019 shipped), second War Room compose, `force` flag, cites backfill, poll, comment-only role.
   - Suggested slice: (1) watchdog filter + `kickoff_turn` including empty-chat + message shape; strip HTTP eager kickoff if present; (2) playbook paragraph on existing PM skill.
   - Tests: human POST → one turn on owning graph including never-chatted; human reply → one turn; agent reply does not loop; resolve does not start a turn; HTTP 202 has no `kickoff` key; wrong graph is not booted; task-tier still 400. A cheap check that `product_manager` SKILL.md contains the comment-thread section is enough for the playbook. Not a mock of `section_slug` or the gate; do not unit-test the LLM.

   **Architect lock (dec_023) — Feature Team honors this when minting. Do not reopen epic decisions.**
   - Filter lives inside existing `deliver_queue_kickoffs`. Do not add a comment watchdog, timer, HTTP-side kickoff, or second subscriber. Every event that consumer sees must ingest/advance the queue offset, including skipped agent `CommentReplied` and `CommentResolved`. Offset is exactly-once: no `kicked_off` sidecar flag, no comment_id dedup table, no sidecar rewrite.
   - `kickoff_turn(kind="comment")` boots the existing owning graph the same way War Room attach does: same graph id, same roster/skills/tools (`resolve_comment` stays unregistered), workspace `resolve_doc_worktree(doc_id)`. Do not boot against trunk. Do not create a throwaway worktree. Do not invent a comment-only graph or a headless LLM runner. Do not add a second tool allowlist.
   - `kind="comment"` is only a KickoffReason tag for logs/tests; the turn path is the existing planning turn.
   - One event → exactly one `kickoff_turn` on that graph. Do not iterate owners/roles.
   - Author filter reads the event/sidecar `author` field: only `human` starts a turn. Do not infer author from HTTP session or War Room attach.
   - If `kickoff_turn` raises, follow existing watchdog retry (keep the event; do not ACK-and-drop; no dead-letter topic).
   - Tests drive POST then `deliver_queue_kickoffs`. Extra cases: `CommentResolved` then a later human POST still fires; agent `reply_comment` writes the worktree sidecar and GET `/api/comments` sees it; no trunk-pointer sidecar; a two-owner epic graph produces one turn not two.
   - Playbook stays one short section on `product_manager` SKILL.md; graph boot must load that skill the same as live chat. Do not inject it via KickoffReason.
   - **Out:** chrome, Resolve, gates, second War Room compose, `force` flag, cites backfill, poll, comment-only role.

   **Product lock (dec_024) — Feature Team honors this when minting. Do not reopen epic decisions.**
   - Operator success #2 is an **in-thread sidecar reply** on the triggering comment, visible on the next GET `/api/comments` or plan reload. Not a spec-only edit, not a new root, not a spinner/poll/toast.
   - Playbook is one short section on existing `product_manager` SKILL.md (loaded by graph boot). Do not inject via KickoffReason. Do not add a skill, role, or graph. Do not copy it onto architect skills. The section contains these rules and nothing more:
     1. This turn is a plan-comment review — read the triggering thread (`comment_id`, `section`, `blocking`, `parent` if reply).
     2. Always `reply_comment` in-thread with `parent` = the triggering `comment_id`. Do not open a new root. A reply that answers, pushes back, or points at a spec/decision update meets the bar.
     3. `write_doc` / `record_decision` on the commented doc are optional extras, not a substitute for the in-thread reply. `propose_epic_amendment` only when an epic contract section would change.
     4. Never resolve, set blocking, dispatch, call `blocking_threads_for`, or re-register `resolve_comment`.
   - No comment-failure toast, spinner, or retry UI — existing watchdog retry (dec_023). Do not require both owners to speak; one in-thread `reply_comment` meets success #2.
   - Tests: cheap SKILL.md contains-check asserts `reply_comment`, in-thread/parent, and the never-list; plus POST then `deliver_queue_kickoffs` yields a sidecar reply with `parent` = the human `comment_id` (including never-attached graphs).
   - Slice unchanged in count: (1) watchdog filter + `kickoff_turn`; (2) playbook paragraph matching the four bullets.
   - **Out:** chrome (feat_017 shipped), Resolve (feat_018 shipped), gates (feat_019 shipped), second War Room compose, `force` flag, cites backfill, poll, comment-only role, HTTP kickoff.

   **Architect lock (dec_025) — Feature Team honors this when minting. Do not reopen epic decisions.**
   - `deliver_queue_kickoffs` and `kickoff_turn` never call `reply_comment` and never append the sidecar. No auto-ack, canned “acknowledged”, or watchdog-written reply to make a test pass.
   - The in-thread reply is only the existing feat_004/005 `reply_comment(comment_id, body)` during the existing planning turn. `comment_id` **is** the parent: the triggering event’s comment id (human root or human reply), not the thread root and not the human row’s `parent`. Do not add a `parent` kwarg, a `review_comment` facade, or a second reply tool. Do not write JSONL by hand.
   - Agents never POST `/api/comment`. That route is always `author=human` (feat_016) and would start another turn.
   - Stored author is the speaking role already in the feat_016 enum (`epic_manager` / `feature_lead` / …). Never `human`. Never a new `comment-reviewer` author. Do not special-case speaker selection on `kind="comment"` — same as live chat.
   - `KickoffReason.message` stays `{role: "human", content: ...}`. `content` is the only channel the model sees (the existing chat transcript). Stable prefix, then a blank line, then the human body verbatim:
     ```
     comment_id: {triggering_id}
     section: {stored_section}
     blocking: true|false
     parent: {human_row_parent}    # omit this line when the human comment is a root

     {human_body}
     ```
     No extra KickoffReason fields the turn loop would drop. No sidecar dump (`line_*`, `doc_sha`, `blocks`, siblings, replies).
   - `kickoff_turn` returns like live-chat kickoff. Do not wait for `reply_comment`. Offset advances when kickoff is accepted, not when a sidecar reply appears. A slow or silent LLM does not stall the queue (retry only if `kickoff_turn` itself raises — dec_023).
   - Do not skip a matching human event because the thread is already resolved. `reply_comment` stays allowed on a resolved thread; the agent does not un-resolve.
   - `reply_comment` must already be on the epic/feature tool list (feat_004/005). Restore that registration if missing. Do not add a `kind="comment"` allowlist (that is how `resolve_comment` would leak back).
   - Tests, without an LLM and without a new harness:
     1. POST → `deliver_queue_kickoffs` → spy/assert exactly one `kickoff_turn(kind="comment")` on the owning graph with that content prefix (including never-attached). Mock `kickoff_turn`. Assert HTTP 202 has no `kickoff` key; agent `CommentReplied` / `CommentResolved` do not call `kickoff_turn`; wrong graph is not booted; task-tier still 400; two-owner graph → one turn.
     2. Call existing `reply_comment(comment_id=human_id, body=...)` as the agent role → GET `/api/comments` sees `parent=human_id`, `author≠human`, worktree sidecar only (no trunk pointer sidecar). Direct tool call. Do not have the watchdog write this row.
     3. Cheap `product_manager` SKILL.md contains-check (dec_024): `reply_comment`, in-thread/parent, never-list.
     4. A POST→watchdog→sidecar-reply test is allowed **only** if the suite already has a scripted/stub planning model. Do not add a new harness, recorded LLM fixture, headless runner, or watchdog auto-ack to satisfy dec_024’s “yields a sidecar reply” wording.
   - **Out:** chrome (feat_017 shipped), Resolve (feat_018 shipped), gates (feat_019 shipped), second War Room compose, `force` flag, cites backfill, poll, comment-only role, HTTP kickoff, watchdog-written reply, new reply tool, new comment author.

4. **[feat_019](../../features/3_completed/feat_019_scoped_dispatch_gates.md) — Scoped dispatch gates** *(completed 2026-10-20; task_083–085 merged)* — One `cascade.comments.blocking_threads_for(work_id)` (work + ancestors, live worktree load) on human dispatch, Boss dispatch, `mint_task`, and feature/task integration merge. No bypass. Optional feature-tier `cites:` frontmatter. Does not gate `mint_feature` or `activate_epic`. Closed before feat_018 (dec_013 miss, accepted as dec_019); **feat_018 has now shipped**, so agent `resolve_comment` is unregistered and the leak is closed. Do not reopen the gate. Body cites on epic_002 children were not promoted to frontmatter; missing `cites:` stays the known limitation (dec_003).

5. **[feat_018](../../features/3_completed/feat_018_human_resolve_and_audit.md) — Human resolve and audit** *(completed 2026-10-20)* — POST `/api/comment/resolve` on an open root only; cascades to descendants; agents cannot resolve; resolved rows stay in JSONL; Resolve control binds to `#plan-comments [data-comment-id]`. **Closeout holds:** human-only resolve shipped; `resolve_comment` is unregistered; the dec_013 leak on the gated tree is closed. feat_020 must not re-register the tool.

**Remaining dispatch (human or Boss):** feat_016, feat_017, feat_018, and feat_019 are complete — do not re-dispatch them. **feat_020 is in planning — do not re-dispatch it.** The Feature Team should mint against `dec_021`, `dec_022`, `dec_023`, `dec_024`, and `dec_025`. HTTP remains enqueue-only (dec_012).

**Cuts still explicit:** no second War Room compose pane, no `force` flag, no gating `mint_feature` / `activate_epic`, `blocks:` API-only, missing `cites:` is a known limitation, no comment polling, no comment-only role, no required spec edit on every comment (an in-thread reply meets success #2; a spec edit is not a substitute), no comment watchdog, no trunk sidecar, no second tool allowlist, no spec-only comment turn, no new-root reply, no comment-failure toast/spinner, no playbook copy onto architect skills, no watchdog auto-reply, no agent HTTP compose, no new comment author, no wait-for-reply inside the watchdog, no new reply tool/facade.

## Open questions

_(none — all resolved, see Decision log dec_001–dec_025)_

## Decision log

The 25 decisions remain on the epic as previously recorded: `dec_001` through `dec_025` (see prior board revision `c6578567a21255af0e6ce5a92579a7734a6e6c5b` and `record_decision` output). Restored in full below from that revision.

- `dec_001` through `dec_024` remain as recorded on the prior board revision `c6578567a21255af0e6ce5a92579a7734a6e6c5b`.

- `dec_025` · 2026-10-20 · Epic Architect · **feat_020 planning — reply write-path and test seam**
  Chose feat_020 Feature Team mints only the existing two-task slice against dec_021–dec_024 plus this write-path lock. deliver_queue_kickoffs and kickoff_turn never call reply_comment and never append the sidecar (no auto-ack). The in-thread reply is only the existing feat_004/005 reply_comment(comment_id, body) during the existing planning turn; comment_id is the parent (the triggering event’s comment id). Agents never POST /api/comment (author is always human on that route). Stored author is the speaking role already in the feat_016 enum, never human, never a new comment-reviewer. KickoffReason.message stays {role: "human", content: ...}; content is the only channel the model sees and uses a stable prefix (comment_id, section, blocking, parent line only if the human row is a reply) then a blank line then the human body verbatim — no extra KickoffReason fields, no sidecar dump. kickoff_turn returns like live chat; offset advances when kickoff is accepted, not when a sidecar reply appears. Do not skip a matching human event because the thread is already resolved; reply_comment stays allowed on a resolved thread; the agent does not un-resolve. Restore the existing reply_comment registration if missing; do not add a kind=comment allowlist. Tests: (1) POST then deliver_queue_kickoffs spies one kickoff_turn(kind="comment") with that content prefix (mock kickoff_turn; no LLM); (2) direct agent-role reply_comment writes the worktree sidecar and GET sees parent=human_id and author≠human; (3) SKILL.md contains-check (dec_024); (4) a POST→watchdog→sidecar-reply path is allowed only if the suite already has a scripted/stub planning model — do not add a harness, recorded fixture, headless runner, or watchdog auto-ack to satisfy dec_024’s “yields a sidecar reply” wording.
  Rationale: feat_020 is in planning. dec_024 required an in-thread sidecar reply and a POST→watchdog test that “yields” that reply, while dec_022 forbids unit-testing the LLM and dec_023 forbids a headless runner. The remaining holes that would ship the wrong reply: the watchdog writing an auto-ack so the test passes without an agent turn; the agent POSTing /api/comment (author=human, starts another turn); comment_id buried in prose or a KickoffReason field the transcript drops so the playbook cannot set parent; kickoff_turn waiting for reply_comment and stalling the queue; skipping a turn after the human resolves; or a new reply tool / comment-reviewer author / kind=comment allowlist that reopens the resolve leak. Locking the write-path and test seam keeps operator success #2 the existing planning turn plus the existing reply_comment tool.
  Honors: dec_012, dec_016, dec_021, dec_022, dec_023, dec_024, dec_005, dec_020; feat_016 enqueue-only POST {ok, comment_id} with author always human and existing reply_comment inherit; feat_017 no-poll chrome; feat_018 human-only resolve (tool unregistered); Intent operator success #2; Kickoff edges only; stacked worktrees / pointer epics; Filesystem is truth; FeaturePlanningStarted feat_020.

## Amendment log

_(none)_
