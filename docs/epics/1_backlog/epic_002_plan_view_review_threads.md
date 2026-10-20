---
id: epic_002
title: Plan-view review threads
tier: epic
status: backlog
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
updated: '2026-10-21'
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
  HTTP POST enqueues only; skipped events still ingest the queue offset (dec_021, dec_022, dec_023)
  Graph boots like War Room attach into resolve_doc_worktree — never trunk (dec_023)

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
- **Kickoff edges only:** Posting a comment enqueues `CommentPosted`; one agent turn is delivered by the watchdog — no timer polling for “new comments on main.” HTTP POST does not start a turn (dec_011, dec_012, dec_021, dec_022, dec_023). Resolve POST also does not start a turn (dec_011, dec_020). Do not add HTTP `kickoff_graph_queue_event` to “fix” cold start. Filter lives inside existing `deliver_queue_kickoffs`; skipped events still advance the offset (dec_023).
- **Stacked worktrees:** Comment sidecars for an active epic/feature live in the same git root as that team’s plan (`resolve_doc_worktree` / existing comment repo rules). A comment `kickoff_turn` uses that same worktree as the graph workspace (dec_005, dec_023); trunk pointers never get a sidecar.
- **Read-only plan renderer** may gain comment *chrome*; plan body edits still go through agent tools or git, not WYSIWYG in the viewer (feat_012 read-only stance unless explicitly extended).
- **Comment chrome is render-only (dec_016).** `line_start` / `line_end` are 1-based markdown source lines from the renderer token source map. Re-anchor and outdated never rewrite the sidecar. `#plan-comments` is upserted by `data-comment-id`, never replaced via `innerHTML`. Task-tier GET `/api/comments` 400 stays. **feat_017 shipped this** (task_080–082). **feat_018 shipped the Resolve button** on that list; do not add a second panel.
- **Blocking is human-only** on create (existing store rule). Agents may reply but not resolve or set blocking. feat_018 shipped the store+tool guard and the Resolve button; `resolve_comment` is unregistered. The dec_013 leak is closed. feat_020 must not re-register the tool.
- **Comment turns are watchdog-only (dec_011, dec_012, dec_021, dec_022, dec_023).** Filter lives inside existing `deliver_queue_kickoffs` (not a second subscriber). It starts `kickoff_turn(kind="comment")` only for human `CommentPosted` / `CommentReplied`. Agent replies and `CommentResolved` ingest the queue offset and do not start a turn; skipped events must still advance the cursor. Offset is exactly-once — no `kicked_off` sidecar flag. One turn per matching event, owning graph only (`epic_{id}` / `feat_{id}` from `doc_id`); do not fan-out to parent epic, child features, or iterate owners/roles. Empty or never-attached graphs still boot **the same way War Room attach does**: same roster/skills/tools (`resolve_comment` stays unregistered), workspace `resolve_doc_worktree(doc_id)` — never trunk, never a throwaway worktree, never a headless comment runner. `kind="comment"` is a KickoffReason tag only; the turn path is the existing planning turn. Author filter is the event/sidecar `author` field (`human` only). `KickoffReason.message` is `{role: "human", content: ...}`. Playbook is one short section on the existing `product_manager` skill (loaded by that boot, not injected as a system prompt) — a `reply_comment` that answers the question meets operator success #2; `write_doc` is optional. No HTTP eager turn, no generic `queue_event` kickoff, no comment-only role, no digest/batch, no second writer, no poll/spinner for the agent reply. If `kickoff_turn` raises, keep the event (existing watchdog retry).
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

feat_016, feat_017, feat_018, and feat_019 are complete. **feat_020 is in planning** (dec_021, dec_022, dec_023). I have not minted tasks.

1. **[feat_016](../../features/3_completed/feat_016_comment_read_api_and_war_room_wiring.md) — Comment read API and War Room wiring** *(completed 2026-10-20; task_077–079 merged)* — GET `/api/comments/{doc_id}` and POST `/api/comment` carry `line_start` / `line_end` / `doc_sha` / `blocks`; `parent` is a reply (section inherited); `cascade.comments.section_slug()` is hyphenated GitHub-style. View plan deep-links to `/plan/{id}#plan-comments`. No second compose form. HTTP `kickoff_graph_queue_event` was **not** added (feat_016 D5 / dec_012); feat_020 owns delivery. Merge must keep one GET `/api/comments` handler. feat_016’s API table still shows a `kickoff` key; **that row is stale** — shipped POST is `202 {ok, comment_id}`.

2. **[feat_017](../../features/3_completed/feat_017_plan_viewer_comment_chrome.md) — Plan viewer comment chrome** *(completed 2026-10-20; task_080–082 merged)* — GitHub-style line threads on `/plan/{id}`: `data-src-line` from markdown source maps, gutter/selection compose, `parent` reply, render-only re-anchor / outdated, `#plan-comments [data-comment-id]` on each root. Blocking checkbox default off. Dropped the 3s poll. Resolve **status** only — the button is feat_018 (dec_007, shipped). POST 202 `{ok, comment_id}` — reload GET; no kickoff wait (dec_012, dec_015, dec_016). Gate (feat_019 shipped) must not read chrome outdated flags (dec_017).

3. **[feat_020](../../features/2_active/feat_020_agent_review_turns.md) — Agent review turns** *(planning 2026-10-20)* — One `kickoff_turn(kind="comment")` per human CommentPosted / CommentReplied, including graphs with no prior chat. Watchdog delivers; HTTP enqueues only (do not add an HTTP eager turn — dec_012, dec_021, dec_022, dec_023). Agent replies and `CommentResolved` do not loop. Playbook on existing `product_manager` skill.

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

4. **[feat_019](../../features/3_completed/feat_019_scoped_dispatch_gates.md) — Scoped dispatch gates** *(completed 2026-10-20; task_083–085 merged)* — One `cascade.comments.blocking_threads_for(work_id)` (work + ancestors, live worktree load) on human dispatch, Boss dispatch, `mint_task`, and feature/task integration merge. No bypass. Optional feature-tier `cites:` frontmatter. Does not gate `mint_feature` or `activate_epic`. Closed before feat_018 (dec_013 miss, accepted as dec_019); **feat_018 has now shipped**, so agent `resolve_comment` is unregistered and the leak is closed. Do not reopen the gate. Body cites on epic_002 children were not promoted to frontmatter; missing `cites:` stays the known limitation (dec_003).

5. **[feat_018](../../features/3_completed/feat_018_human_resolve_and_audit.md) — Human resolve and audit** *(completed 2026-10-20)* — POST `/api/comment/resolve` on an open root only; cascades to descendants; agents cannot resolve; resolved rows stay in JSONL; Resolve control binds to `#plan-comments [data-comment-id]`. **Closeout holds:** human-only resolve shipped; `resolve_comment` is unregistered; the dec_013 leak on the gated tree is closed. feat_020 must not re-register the tool.

**Remaining dispatch (human or Boss):** feat_016, feat_017, feat_018, and feat_019 are complete — do not re-dispatch them. **feat_020 is in planning — do not re-dispatch it.** The Feature Team should mint against `dec_021`, `dec_022`, and `dec_023`. HTTP remains enqueue-only (dec_012).

**Cuts still explicit:** no second War Room compose pane, no `force` flag, no gating `mint_feature` / `activate_epic`, `blocks:` API-only, missing `cites:` is a known limitation, no comment polling, no comment-only role, no required spec edit on every comment (a reply meets success #2), no comment watchdog, no trunk sidecar, no second tool allowlist.

## Open questions

_(none — all resolved, see Decision log dec_001–dec_023)_

## Decision log

- `dec_001` · 2026-10-18 · Epic Architect · **Anchor model**
  Chose line-level threads for MVP, GitHub-style; root comment stores line_start/line_end, section slug, anchor snippet, and doc_sha; when the doc sha changes, re-anchor by snippet within section, else show as section-level "outdated" (never dropped, still blocking if blocking).
  Rationale: Human asked for comments as close as possible to where they are relevant, at the line like GitHub; doc_sha makes the outdated check cheap and deterministic
  Honors: human feedback 2026-10-18; Intent (GitHub-style review); read-only plan renderer constraint.

- `dec_002` · 2026-10-18 · Epic Architect · **Default blocking**
  Chose an opt-in blocking checkbox on root comments, unchecked by default; only humans may set it.
  Rationale: Human confirmed a checkbox to force a comment to be blocking; matches DESIGN today and avoids gating all work on casual comments
  Honors: human feedback 2026-10-18; Blocking is human-only constraint.

- `dec_003` · 2026-10-18 · Epic Architect · **Cross-doc scope**
  Chose scope precedence: (a) explicit blocks: [work_id] on the root comment; else (b) a section thread on an epic blocks the epic plus only child features whose frontmatter cites: includes {epic_id}#{section_slug}; else (c) a section thread on a feature, or any doc-level thread, blocks the doc and all its children; tasks inherit blocking from their parent feature; one shared section_slug() is used by viewer and gate, and cites matching no current heading are reported as warnings.
  Rationale: Human confirmed only features whose specs cite that section should be blocked; explicit cites avoid fragile inference. Known limitation: a feature missing its cites: entry is not blocked by section threads
  Honors: human feedback 2026-10-18; Intent human gate; Scope constraint.

- `dec_004` · 2026-10-18 · Epic Architect · **Boss dispatch**
  Chose one shared gate blocking_threads_for(work_id) called by human War Room dispatch, Boss auto-dispatch, mint_task, and merge, with no bypass or force flag; the human unblocks by resolving the thread.
  Rationale: Delegated to the team by the human; a second code path or override flag is where the human gate would leak, and resolving is one click
  Honors: Intent human gate (dispatch and merges); Dispatch law unchanged constraint.

- `dec_005` · 2026-10-18 · Epic Architect · **Pointer epics on trunk**
  Chose all comment reads/writes for an active epic resolve to the epic worktree spec via resolve_doc_worktree (feat_014); trunk pointers never get their own sidecar; line anchors always refer to the worktree spec, and the sidecar merges to trunk with the spec at closeout.
  Rationale: Delegated to the team by the human; a single sidecar per live spec keeps anchors and doc_sha consistent and needs no sync logic
  Honors: Stacked worktrees constraint; Filesystem is truth.

- `dec_006` · 2026-10-18 · Epic Architect · **section_slug ownership**
  Chose `section_slug()` owned by feat_016 in `cascade/comments/`, imported by the viewer and the gate. The gate feature does not grow a second slugger.
  Rationale: Viewer and gate both persist/match section slugs. Putting the function on the comment store (shipped first) prevents two implementations from drifting.
  Honors: dec_003; feat_016 comment contract; Cross-module constraints.

- `dec_007` · 2026-10-18 · Epic Architect · **Resolve ownership**
  Chose human resolve control as feat_018. feat_017 renders open vs resolved only. Dispatch feat_018 in the same wave as feat_017.
  Rationale: Agent tools can still resolve today. The button and the store/tool guard belong together so chrome does not ship a control that agents can race.
  Honors: Intent (resolved only as human); Blocking is human-only constraint.

- `dec_008` · 2026-10-18 · Epic Architect · **Section vs doc-level**
  Chose a root comment always has a non-empty section slug. It is a section thread iff that slug matches a current ## or deeper heading on the commented doc (via section_slug). Otherwise it is doc-level (H1 title slug, general, or unmatched). Epic rule (b) applies only to epic section threads. Never persist empty section.
  Rationale: The store already refuses empty section, and the viewer always has a nearest heading or the document title. Matching against live ##+ headings makes gate rule (b) vs (c) deterministic without a second scope field.
  Honors: dec_003; feat_016 required section; Intent human gate.

- `dec_009` · 2026-10-18 · Epic Architect · **Thread-level resolve**
  Chose POST /api/comment/resolve is allowed only on an open root. It marks that root and all descendants resolved. Resolving a reply returns 400. Agents still cannot resolve.
  Rationale: Closeout already blocks on any open human comment, including in-thread replies. GitHub resolves the conversation, not one line. Cascading avoids a footgun where resolving the root still leaves the operator's reply blocking complete.
  Honors: Intent (resolved only as human); completion rollup (any open human thread).

- `dec_010` · 2026-10-18 · Epic Architect · **Gate scans ancestors**
  Chose blocking_threads_for(work_id) loads open blocking roots from the work itself, its parent feature (if a task), and its parent epic, then applies dec_003 scope to decide membership. It does not only look at comments stored on work_id.
  Rationale: Epic-section threads live on the epic sidecar. A gate that only reads the feature's own comments would never see them, which would break dec_003.
  Honors: dec_003; dec_004; Intent human gate.

- `dec_011` · 2026-10-18 · Epic Architect · **Watchdog-only comment kickoff**
  Chose one helper, watchdog-delivered: human CommentPosted/CommentReplied start kickoff_turn(kind=comment) with message {role: human, content: ...}. Agent comment events and CommentResolved ingest the queue offset and do not start a turn. HTTP POST /api/comment enqueues only; feat_016 may keep today's eager kickoff_graph_queue_event until feat_020 replaces it.
  Rationale: Generic queue_event kickoff no-ops on empty chat and would also fire on resolve. Filtering event types on the existing watchdog edge is the smallest fix that meets operator success #2 without a reply or resolve loop.
  Honors: Kickoff edges only; feat_018 no turn on resolve; feat_020 human-only comment turns.

- `dec_012` · 2026-10-20 · Epic Manager · **feat_016 closeout — kickoff delivery**
  Chose Accept feat_016 D5: POST /api/comment does not call kickoff_graph_queue_event and does not return a kickoff key. feat_020 implements watchdog-only comment turns and must not add an HTTP eager turn. If uncommitted main work that adds that call is merged first, feat_020 removes it. Merge of feat_016 must keep a single GET /api/comments handler (drop the duplicate _handle_comments vs _handle_comments_list).
  Rationale: feat_016 was cut from a committed base that had no kickoff helper; adding one there would have duplicated in-flight main work and raced feat_020. Operator success #2 (owning team replies in-thread) is feat_020's job, not a silent HTTP side effect. Duplicate GET handlers would make the locked read API non-deterministic.
  Honors: feat_016 D5; dec_011; Kickoff edges only; Operator success #2.

- `dec_013` · 2026-10-20 · Epic Architect · **Scoped dispatch gates — merge order**
  Chose feat_019 may be implemented in parallel after feat_016 but must not merge or close out before feat_018. Until resolve is human-only, agents can still resolve_comment and that would bypass the gate. depends_on stays feat_016 (comment schema only).
  Rationale: dec_004 is one shared gate with no bypass; the human unblocks by resolving. feat_018 is what takes resolve_comment off agent tools and puts the Resolve button on the plan. Shipping the gate first would let the owning team unblock dispatch without a human click. Schema work can still proceed in parallel; only closeout waits.
  Honors: dec_004; dec_007; Intent human gate (dispatch and merges); feat_018 D1 agents cannot resolve.

- `dec_014` · 2026-10-20 · Epic Architect · **017/018 parallel dispatch**
  Chose feat_018 depends_on is feat_016 only, not feat_017. feat_017 and feat_018 may dispatch and merge in either order. Shared contract: each root thread in #plan-comments is an element with data-comment-id equal to the root comment id. feat_017 emits it (and must not wipe a Resolve control already mounted); feat_018 binds Resolve to open roots (and stamps the attribute if chrome has not shipped). Doc-level re-anchor on feat_017 searches the whole body, not an H1-only range.
  Rationale: dec_007 already says dispatch 017 and 018 in the same wave, but feat_018.depends_on still listed feat_017, which would block resolve until chrome is complete. The store and tool guard do not need chrome; the existing #plan-comments panel is enough for a Resolve button. A second depends_on would also prevent leaving and resolving a thread in one operator session. The data-comment-id marker is the smallest seam that lets either merge order work without both features owning the list innerHTML.
  Honors: dec_007; Intent (resolved only as human); feat_016 existing #plan-comments panel; feat_018 D1 agents cannot resolve.

- `dec_015` · 2026-10-20 · Epic Manager · **feat_017 planning — viewer consumer contract**
  Chose feat_017 Feature Team consumes the shipped feat_016 API as-is and mints only chrome tasks. POST /api/comment returns 202 {ok, comment_id} with no kickoff key (dec_012); after compose or reply, reload GET /api/comments/{doc_id} and do not wait for a turn or add polling. Import cascade.comments.section_slug; do not fork it. Persist doc_sha as the currently rendered spec blob sha (the same sha read_doc / GET /api/doc/{id} already use — add sha on that JSON if missing; do not hash innerText). Compose posts line_start/line_end, section (nearest heading slug, never empty), anchor snippet, doc_sha, and blocking default false. No blocks picker (API-only). No Resolve button (feat_018). Each #plan-comments root is an element with data-comment-id equal to the root id; do not wipe a Resolve control already mounted (dec_014). Section-thread re-anchor searches that heading's range; doc-level re-anchor searches the whole body (dec_014); unmatched threads show outdated at section/doc level and stay listed (still blocking if blocking). Task plans stay comment-read-only (no gutter). Plan body stays read-only (no WYSIWYG). Parallel with feat_018; either merge order.
  Rationale: FeaturePlanningStarted for feat_017. The remaining hole is the Feature Team reading feat_016's stale API table (202 includes kickoff) or gold-plating compose (blocks picker, Resolve, poll, client-hashed sha). Locking the shipped consumer contract keeps chrome the smallest slice that meets operator success #1 without reopening dec_001–014 or racing feat_018/020.
  Honors: dec_001, dec_002, dec_006, dec_007, dec_008, dec_012, dec_014; feat_016 D5 shipped POST shape; Intent operator success #1; explicit cuts (no second War Room compose, blocks API-only, no poll, no WYSIWYG); FeaturePlanningStarted feat_017.

- `dec_016` · 2026-10-20 · Epic Architect · **feat_017 planning — render/store seam**
  Chose feat_017 chrome is render-only against the shipped feat_016 sidecar. line_start/line_end are 1-based markdown source lines from the renderer token source map (data-src-line on each block) — not rendered-DOM index, innerText split, or CSS line boxes. Re-anchor and outdated are display-only: never PATCH/re-POST an existing root to move lines, section, or doc_sha; stored fields stay as posted; re-anchor runs only when the currently rendered worktree blob sha differs from stored doc_sha. After GET reload, upsert #plan-comments nodes keyed by data-comment-id; never assign innerHTML on the list container; outdated and resolved roots keep the attribute so feat_018 can still bind Resolve. Reply POST is {doc_id, body, parent} only — do not send section/line/sha/blocks/blocking (feat_016 inherits and ignores extras). Nearest heading is the owner of line_start (walk source backward to nearest ## or deeper; if none, H1 slug or general); a selection that spans headings is still one root. Task-tier GET /api/comments 400 stays: no gutter, no compose, no new task comment route. The only allowed API addition is sha on GET /api/doc/{id} if missing, and that sha is the worktree spec blob via resolve_doc_worktree, never the trunk pointer body. One #plan-comments panel (feat_016 already has it). Do not add a second list, poll, kickoff wait, blocks picker, or Resolve button.
  Rationale: FeaturePlanningStarted for feat_017. dec_015 already locked the shipped POST/GET consumer contract. The remaining holes are chrome inventing a second line-number space (breaking GitHub-style anchors and dec_001), rewriting sidecar anchors after a doc edit (which would make stored doc_sha and section lie to feat_019), wiping a Resolve button on reload (dec_014), posting reply metadata that feat_016 must ignore, or lifting the task-tier 400. Locking the render/store seam keeps operator success #1 the smallest slice and stops a race with feat_018/019/020.
  Honors: dec_001, dec_005, dec_006, dec_008, dec_014, dec_015; feat_016 shipped parent-inherit and task-tier 400; Intent operator success #1; read-only plan renderer; Filesystem is truth; stacked worktrees / pointer epics.

- `dec_017` · 2026-10-20 · Epic Manager · **feat_019 planning — one store-side gate**
  Chose feat_019 Feature Team mints only gate tasks against the locked scope (dec_003/004/008/010) and merge wait (dec_013). One function blocking_threads_for(work_id) is the entire product: (1) Load open blocking root comments from the work and its ancestors (parent feature if a task, parent epic) via the existing sidecar + resolve_doc_worktree. Do not read plan-viewer DOM, outdated flags, or line numbers. Replies never participate; resolved and non-blocking roots never participate. (2) Membership uses dec_003 precedence on stored section/blocks plus current worktree ##+ headings via imported cascade.comments.section_slug — do not fork it. Outdated chrome is display-only (dec_016): an unmatched snippet still blocks if the root is blocking. (3) Replace (do not stack on) the existing mint_task "any blocking comment on this feature" check. Wire the same function into human War Room dispatch, Boss auto-dispatch, mint_task, and merge. No force flag, no second code path. Do not gate mint_feature or activate_epic. Closeout rollup is unchanged (any open human thread still blocks complete) — do not fold closeout into this function. (4) Add optional WorkMeta.cites: list[str] as {epic_id}#{section_slug}, already hyphenated. Do not infer cites from spec prose. Missing cites is the known limitation (dec_003). Cites that match no current heading are warnings on the refusal, not silent and not a hard fail. Backfill cites: on epic_002's children from the cites already listed in those spec bodies so rule (b) is testable. (5) Refusal lists thread id, doc_id, section, and a /plan/{doc_id}#plan-comments link. Unknown blocks: ids are ignored. (6) Must not merge or close out before feat_018's agent-tool resolve denial is on the board (dec_013). Implementation may proceed; depends_on stays feat_016. Out of this feature: Resolve button (feat_018), chrome (feat_017 shipped), agent kickoff (feat_020), blocks picker, cite inference, force flag, second slugger, gating activate_epic/mint_feature, changing closeout, sidecar rewrite. Suggested slice: (1) cites: + blocking_threads_for membership tests; (2) four call sites + replace mint_task check + refusal payload. High-signal tests are dispatch/mint_task/merge API tests (epic-section + cites hit/miss, feature-section blocks tasks, doc-level blocks all children, blocks: override, ancestor scan, non-blocking/resolved do not refuse, Boss path equals human). Not a unit mock of section_slug.
  Rationale: FeaturePlanningStarted for feat_019 after feat_017 closeout. The remaining holes are stacking the old mint_task any-blocking rule (stricter than dec_003), missing Boss or merge (the leak dec_004 forbids), gating closeout or mint_feature/activate_epic, skipping outdated threads, inferring cites from prose, or merging before feat_018. Locking the store-side consumer contract keeps operator success #3 the smallest slice and stops a race with feat_018.
  Honors: dec_003, dec_004, dec_006, dec_008, dec_010, dec_013, dec_016; feat_016 shipped sidecar and section_slug; Intent operator success #3 (unresolved blocking threads stop dispatch/merge); explicit cuts (no force flag, no cite inference, blocks API-only, no gating mint_feature/activate_epic); FeaturePlanningStarted feat_019.

- `dec_018` · 2026-10-20 · Epic Architect · **feat_019 planning — call-site and worktree seam**
  Chose blocking_threads_for as a pure Python function next to the comment store (cascade.comments.blocking_threads_for), imported by every mutating call site — not a War Room HTTP helper, not JS, not a second copy in Boss. Each call live-loads ancestor sidecars and feature cites through resolve_doc_worktree (never trunk pointers, never a boot-time cache, never plan-viewer JS). WorkMeta.cites is optional and feature-tier only; the gate reads frontmatter only (no prose inference); backfill epic_002 children from the cites already listed in those spec bodies. blocks: non-empty is an exclusive membership set (listed ids plus tasks of listed features); do not union with (b)/(c). Compare stored section as-is to live section_slug(##+) headings — do not re-slugify historical free-text; unmatched is doc-level (dec_008), no heading snapshot, no fuzzy rename match. mint_task(feature_id) gates on blocking_threads_for(feature_id); dispatch_task/merge of a task gate on the task id (ancestor scan + inherit). Merge means the existing feature/task integration merge for that work_id, not git commit and not closeout rollup. Return the in-scope blocking roots; empty means allow. Call sites reuse the existing War Room/Boss refusal shape (not 500); payload lists thread id, doc_id, section, /plan/{doc_id}#plan-comments; unmatched-cite warnings ride along and never refuse by themselves. No writes, queue events, or sidecar rewrites. Must not merge before feat_018 (dec_013). Out of this feature unchanged.
  Rationale: FeaturePlanningStarted for feat_019. dec_017 locked the store-side consumer contract. Remaining holes: putting the gate in War Room HTTP only (Boss/merge would bypass), caching comments at graph boot (resolve would not unblock in-process), reading trunk pointer specs/sidecars (dec_005), inferring cites from the 'Cites (promote...' body line at runtime, unioning blocks: with section scope, re-slugifying historical 'Open questions' rows or snapshotting headings to preserve rule (b) after a rename, or gating closeout/git commit. Locking the call-site/worktree seam keeps operator success #3 the smallest slice and stops a leak of the human gate.
  Honors: dec_003, dec_004, dec_005, dec_008, dec_010, dec_013, dec_017; feat_016 shipped sidecar, section_slug, resolve_doc_worktree; Intent operator success #3; Filesystem is truth; stacked worktrees / pointer epics; Dispatch law unchanged; FeaturePlanningStarted feat_019.

- `dec_019` · 2026-10-20 · Epic Manager · **feat_019 closeout — gate shipped ahead of resolve**
  Chose Accept feat_019 closeout (task_083–085): cascade.comments.blocking_threads_for live-loads work+ancestors via sidecar + resolve_doc_worktree, is imported by human/Boss dispatch, mint_task (replacing the old any-blocking-comment check), and feature/task integration merge, with no force flag. WorkMeta.cites is optional and feature-tier only. Do not reopen or roll back the gate. Sequencing vs dec_013 was missed: feat_019 closed while feat_018 is still active, so agent resolve_comment still exists on the gated tree until feat_018 merges. feat_018 task_086 already implements the store+tool guard; merging feat_018 is the leak close, not a new gate task. cites: were not copied onto epic_002 children frontmatter; keep the known missing-cites limitation (dec_003) rather than minting a backfill task — Feature Teams copy the body cites line into YAML on their next spec edit.
  Rationale: FeatureCompleted for feat_019. The shipped function and four call sites meet operator success #3 and dec_017/dec_018. Rolling the gate back would cut a working human gate to wait on chrome/resolve process order. The remaining hole is agent resolve_comment on that tree, which is already feat_018's job (task_086 done, task_087 in flight). A cites linter or backfill feature would be gold-plating of a limitation we already accepted.
  Honors: dec_003, dec_004, dec_005, dec_006, dec_008, dec_010, dec_013, dec_017, dec_018; feat_016 shipped sidecar and section_slug; Intent operator success #3; explicit cuts (no force flag, no cite inference, no gating mint_feature/activate_epic); FeatureCompleted feat_019.

- `dec_020` · 2026-10-20 · Epic Manager · **feat_018 planning — human resolve is the leak close**
  Chose feat_018 Feature Team finishes only the remaining resolve slice against shipped chrome and the already-landed store guard. task_086 is done: resolve_comment requires author=human, cascades root+descendants, refuses non-roots, copies feat_016 fields on rewrite, and is unregistered from epic/feature tools. task_087 is the rest: POST /api/comment/resolve {doc_id, comment_id} with author forced to human — 202 {ok, comment_id}, 404 missing, 400 NotARoot on a reply, idempotent 202 on an already-resolved root; no kickoff_graph_queue_event or kickoff_turn. Resolve button on each open root in #plan-comments [data-comment-id]; none on replies or resolved roots; click then reload GET. Chrome has shipped (feat_017): mount inside the existing list render; do not add a second panel, poll, or WYSIWYG. Recreating the button on chrome's existing re-render is OK; do not re-register resolve_comment on agent tools. Do not re-implement blocking_threads_for. Merge of this feature is what closes the dec_013 leak on the gated tree. YAML may still list depends_on: feat_017; ignore it (dec_014). Out: unresolve, hide-resolved, second auth layer, comment polling, gates, HTTP eager turn, blocks picker, a new cites-backfill task.
  Rationale: feat_018 is active with task_087 in flight after feat_019 closeout. The hole is gold-plating resolve (unresolve, poll, a second list) or re-opening the gate, which would delay the human click that operator success #3 now depends on. Locking the remaining slice keeps resolve the smallest un-bypass of the shipped gate.
  Honors: dec_007, dec_009, dec_011, dec_013, dec_014, feat_016 shipped POST/GET, feat_017 shipped data-comment-id chrome, feat_018 D1–D6, Intent (resolved only as human), Feature active feat_018.

- `dec_021` · 2026-10-20 · Epic Architect · **feat_020 planning — kickoff/delivery seam**
  Chose feat_020 Feature Team mints only watchdog-delivery tasks against dec_011/dec_012. Watchdog deliver_queue_kickoffs is the only path that starts a turn: event in {CommentPosted, CommentReplied} AND author=human. Agent CommentReplied, CommentResolved, and every other event ingest the queue offset and do not start a turn. One kickoff_turn(kind="comment") per matching event, on the owning graph only (epic_{id} / feat_{id} from doc_id). Task-tier comments stay 400 — no task graph turn and no parent-fanout. KickoffReason.message is {role: "human", content: ...} — content is the human body plus comment_id, section, blocking, and parent if reply; not a system prompt and not the whole sidecar. Empty or never-attached graphs must still run: kickoff_turn boots the owning graph if needed. Do not require War Room attach. Do not add HTTP kickoff_graph_queue_event to "fix" cold start; if that call exists on POST /api/comment, delete it (dec_012). Playbook is a short section on the existing product_manager skill; the owning graph's existing turn loop runs — do not add a comment-only role or a second graph. Agent may reply_comment and optionally write_doc / record_decision; propose_epic_amendment only when an epic contract section would change. Never resolve, never set blocking, never dispatch, never call blocking_threads_for, never re-register resolve_comment (feat_018 closeout holds; the dec_013 leak stays closed). Agent reply_comment uses the existing sidecar via resolve_doc_worktree. No second writer, no poll, no chrome change, no new queue topic, no timer, no digest/batch, no sidecar rewrite of line/section/doc_sha. Out of this feature: Resolve button (feat_018 shipped), gates (feat_019 shipped), second War Room compose, force flag, cites backfill.
  Rationale: feat_018 is complete (human-only resolve shipped) and feat_020 is in planning. dec_011/dec_012 already forbid an HTTP eager turn and a resolve/reply loop. The remaining holes are using generic queue_event kickoff (no-ops on empty chat and would fire on CommentResolved), adding HTTP kickoff_graph_queue_event to "fix" cold start, booting the wrong graph or a comment-only role, dumping a system prompt or the whole sidecar into KickoffReason.message, batching pending comments into a digest, or re-registering resolve_comment and reopening the gate leak. Locking the kickoff/delivery seam keeps operator success #2 the smallest slice that still replies in-thread on a never-attached graph.
  Honors: dec_011, dec_012, dec_005, dec_013, dec_019, dec_020; feat_016 shipped enqueue-only POST {ok, comment_id} and task-tier 400; feat_017 shipped no-poll chrome; feat_018 shipped human-only resolve; Intent operator success #2; Kickoff edges only; stacked worktrees / pointer epics; FeaturePlanningStarted feat_020.

- `dec_022` · 2026-10-20 · Epic Manager · **feat_020 planning — operator success #2 slice**
  Chose feat_020 Feature Team mints only watchdog-delivery plus playbook tasks against dec_011/dec_012/dec_021. Operator success #2 is: a human comment on an epic or feature plan produces one owning-team turn, and an in-thread reply may appear on the next GET / plan reload — not a spinner, poll, websocket, or second War Room compose. Playbook is one short section on the existing product_manager skill (already used by epic_manager and feature_lead); do not add a skill file, a comment-only role, or a second graph; do not inject the playbook as a KickoffReason system prompt. A reply_comment that answers the question meets the bar; write_doc / record_decision are optional; propose_epic_amendment only when an epic contract section would change. Never resolve, never set blocking, never dispatch, never call blocking_threads_for, never re-register resolve_comment. POST /api/comment stays 202 {ok, comment_id} with no kickoff key; if kickoff_graph_queue_event exists on that route, delete it. One kickoff_turn(kind="comment") per human CommentPosted/CommentReplied on the owning graph only (doc_id → epic_{id} / feat_{id}); empty/never-attached graphs boot; task-tier stays 400; do not fan-out to the parent epic or child features. Agent CommentReplied and CommentResolved ingest the queue offset and do not start a turn. Slice unchanged: (1) watchdog filter + kickoff_turn including empty-chat + message shape; strip HTTP eager kickoff if present; (2) playbook paragraph on the existing PM skill. High-signal tests: human POST → one turn on the owning graph including a never-chatted graph; human reply → one turn; agent reply does not loop; resolve does not start a turn; HTTP 202 has no kickoff key; wrong graph is not booted; task-tier still 400. A cheap check that product_manager SKILL.md contains the comment-thread section is enough for the playbook. Not a mock of section_slug or the gate; do not unit-test the LLM. Out: chrome (feat_017 shipped), Resolve button (feat_018 shipped), gates (feat_019 shipped), second War Room compose, force flag, cites backfill, poll, comment-only role.
  Rationale: feat_020 is in planning and dec_021 already locked the kickoff/delivery seam. Remaining product holes are gold-plating the playbook into a new role or a system prompt, requiring a spec edit on every comment, bringing back poll/live-wait for the agent reply (feat_017 dropped the 3s poll), fanning out to parent/child graphs, or putting kickoff back on HTTP so tests skip the watchdog. Locking the operator slice keeps success #2 the smallest shippable in-thread reply path.
  Honors: dec_011, dec_012, dec_021, dec_005, dec_020; feat_016 shipped enqueue-only POST {ok, comment_id} and task-tier 400; feat_017 shipped no-poll chrome; feat_018 shipped human-only resolve; Intent operator success #2; Kickoff edges only; explicit cuts (no second War Room compose, no force flag, no cites backfill, no poll); FeaturePlanningStarted feat_020.

- `dec_023` · 2026-10-20 · Epic Architect · **feat_020 planning — graph boot and queue-consumer seam**
  Chose feat_020 Feature Team mints only watchdog-delivery plus playbook tasks against dec_011/dec_012/dec_021/dec_022. Filter lives inside existing deliver_queue_kickoffs (the same consumer live-chat already uses) — not a comment watchdog, timer, HTTP-side kickoff, or second subscriber. Every event that consumer sees must ingest/advance the queue offset, including skipped agent CommentReplied and CommentResolved; the offset is the exactly-once mechanism. Do not persist kicked_off on the comment row, do not add a comment_id dedup table, and do not rewrite the sidecar. kickoff_turn(kind="comment") boots the existing owning graph the same way War Room attach does: same graph id (epic_{id} / feat_{id} from doc_id), same roster/skills/tools (resolve_comment stays unregistered), same workspace via resolve_doc_worktree(doc_id). Do not boot against trunk, do not create a throwaway worktree, do not invent a comment-only graph or a headless LLM runner, and do not add a second tool allowlist (that is how resolve_comment would leak back). kind="comment" is only a KickoffReason tag for logs/tests; the turn path is the existing planning turn. One event → exactly one kickoff_turn on that graph; do not iterate owners/roles (two replies to one comment). Author filter reads the event/sidecar author field: only human starts a turn; missing/agent/other never does — do not infer author from HTTP session or War Room attach. If kickoff_turn raises, follow existing watchdog retry for failed live-chat kickoffs (keep the event; do not ACK-and-drop; no dead-letter topic). Tests drive POST then deliver_queue_kickoffs (or the watchdog helper the suite already uses); do not add HTTP kickoff to make tests pass. Extra cases on those same tests: CommentResolved then a later human POST still fires (offset advanced); agent reply_comment writes the worktree sidecar and GET /api/comments sees it; no trunk-pointer sidecar is created; a two-owner epic graph produces one turn not two. Playbook stays one short section on product_manager SKILL.md; graph boot must load that skill the same as live chat so the paragraph is in context — do not inject it via KickoffReason. Out of this feature unchanged: chrome, Resolve, gates, second War Room compose, force flag, cites backfill, poll, comment-only role.
  Rationale: feat_020 is in planning. dec_021 locked the kickoff/delivery seam and dec_022 locked the operator slice. Remaining holes that would ship the wrong in-thread reply: a parallel comment consumer that skips CommentResolved without advancing the offset (watchdog stalls, later comments never fire); booting the graph against trunk or a throwaway worktree so reply_comment writes a sidecar the plan viewer never reads (dec_005); a headless comment runner that omits the product_manager skill (playbook never runs) or a second tool allowlist that re-registers resolve_comment (reopens the dec_013 leak); iterating owners so one human comment gets two agent replies; inferring author from HTTP/attach; or adding HTTP kickoff so tests skip the watchdog (dec_012). Locking the graph-boot and queue-consumer seam keeps operator success #2 the smallest slice that still replies in the worktree sidecar on a never-attached graph.
  Honors: dec_005, dec_011, dec_012, dec_013, dec_016, dec_018, dec_021, dec_022; feat_016 shipped enqueue-only POST {ok, comment_id} and task-tier 400; feat_017 shipped no-poll chrome; feat_018 shipped human-only resolve (tool unregistered); feat_019 shipped store-only gate; Intent operator success #2; Kickoff edges only; stacked worktrees / pointer epics; Filesystem is truth; FeaturePlanningStarted feat_020.

- `dec_024` · 2026-10-20 · Epic Manager · **feat_020 planning — in-thread reply and playbook text**
  Chose feat_020 Feature Team mints only the existing two-task slice against dec_021/dec_022/dec_023 plus this playbook lock. Operator success #2 is an in-thread sidecar reply on the triggering comment, visible on the next GET /api/comments or plan reload — not a spec-only edit, not a new root, not a spinner/poll/toast. Playbook is one short section on the existing product_manager SKILL.md (loaded by graph boot the same as live chat; do not inject via KickoffReason; do not add a skill, role, or graph; do not copy it onto architect skills). The section must contain these rules and nothing more: (1) This turn is a plan-comment review — read the triggering thread (comment_id, section, blocking, parent if reply). (2) Always reply_comment in-thread with parent = the triggering comment_id; do not open a new root. A reply that answers, pushes back, or points at a spec/decision update meets the bar. (3) write_doc / record_decision on the commented doc are optional extras, not a substitute for the in-thread reply; propose_epic_amendment only when an epic contract section would change. (4) Never resolve, set blocking, dispatch, call blocking_threads_for, or re-register resolve_comment. No comment-failure toast, spinner, or retry UI — existing watchdog retry (dec_023). Do not require both owners to speak; one in-thread reply_comment meets success #2. Tests: cheap SKILL.md contains-check asserts reply_comment, in-thread/parent, and the never-list; plus POST then deliver_queue_kickoffs yields a sidecar reply with parent = the human comment_id (including never-attached graphs). Out unchanged: chrome, Resolve, gates, second War Room compose, force flag, cites backfill, poll, comment-only role, HTTP kickoff..
  Rationale: dec_023 closed graph-boot and queue-consumer holes. Remaining product holes that would fail operator success #2: a spec-only turn with no in-thread reply, a new-root comment that is not in-thread, a long playbook that invents a reviewer workflow or copies onto architect skills, or a failure toast/poll because kickoff_turn can raise. Locking the playbook to those four bullets keeps the skill edit the smallest thing that still shows a team reply on reload.
  Honors: dec_021, dec_022, dec_023, dec_012, dec_005, dec_020; feat_016 enqueue-only POST {ok, comment_id}; feat_017 no-poll chrome; feat_018 human-only resolve; Intent operator success #2; Kickoff edges only; explicit cuts (no second War Room compose, no poll, no comment-only role, no required spec edit); FeaturePlanningStarted feat_020..
## Amendment log

_(none)_
