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
  └─ POST /api/comment (root or parent reply); POST /api/comment/resolve

docs/_comments/{doc_id}.jsonl          [unchanged store; richer anchor fields]
        │
        ▼ CommentPosted / CommentReplied
Epic graph or Feature graph (owning doc_id)
        │
        ├─ reply_comment / write_doc / record_decision
        ├─ resolve is human-only, thread-level (feat_018); agents do not get the tool
        └─ optional: propose_epic_amendment when epic section changes

Watchdog deliver_queue_kickoffs → kickoff_turn(kind="comment") for human authors (feat_020)
  HTTP POST enqueues only; CommentResolved and agent replies do not start a turn

Dispatch law + new scope gates (feat_019 planning)
  ├─ cascade.comments.blocking_threads_for live-loads work+ancestors; refuse dispatch/mint_task/merge
  └─ completion rollup unchanged: any open human thread still blocks closeout
```

**Owning team:** epic-tier `doc_id` → graph `epic_{id}`; feature-tier `doc_id` → graph `feat_{id}`. Task plans are read-only for comments in v1 (tasks have no room; operator comments on parent feature or epic).

## Cross-module constraints

- **Filesystem is truth.** Comments remain sidecars, not inline in the `.md` body (feat_005 / DESIGN §10.3).
- **Localhost only.** Plan viewer and APIs stay on `127.0.0.1`; no GitHub OAuth or remote PR comments.
- **Dispatch law unchanged:** Epic activate = human only; feature/task dispatch = human or Boss. Agents still cannot dispatch themselves.
- **Kickoff edges only:** Posting a comment enqueues `CommentPosted`; one agent turn is delivered by the watchdog — no timer polling for “new comments on main.” HTTP POST does not start a turn (dec_011, dec_012).
- **Stacked worktrees:** Comment sidecars for an active epic/feature live in the same git root as that team’s plan (`resolve_doc_worktree` / existing comment repo rules).
- **Read-only plan renderer** may gain comment *chrome*; plan body edits still go through agent tools or git, not WYSIWYG in the viewer (feat_012 read-only stance unless explicitly extended).
- **Comment chrome is render-only (dec_016).** `line_start` / `line_end` are 1-based markdown source lines from the renderer token source map. Re-anchor and outdated never rewrite the sidecar. `#plan-comments` is upserted by `data-comment-id`, never replaced via `innerHTML`. Task-tier GET `/api/comments` 400 stays. **feat_017 shipped this** (task_080–082).
- **Blocking is human-only** on create (existing store rule). Agents may reply but not resolve or set blocking.
- **Gate is store-only (dec_017, dec_018).** `cascade.comments.blocking_threads_for(work_id)` is a pure function next to the comment store. Each call live-loads open blocking roots from the work and ancestors via sidecar + `resolve_doc_worktree` (never trunk pointers, never a boot-time cache, never plan-viewer JS). It reads current worktree `##+` headings. It does not consult outdated state, line numbers, or rewrite comments. Replace the existing `mint_task` any-blocking check; do not stack. Do not gate `mint_feature` or `activate_epic`. Closeout rollup stays separate. Merge means the existing feature/task integration merge for that `work_id`, not git commit.
- **Scope (locked, see dec_003/dec_004/dec_008/dec_010/dec_018):** affected work for an open blocking *root* thread, in order of precedence:
  (a) explicit `blocks: [work_id, …]` on the root comment, if **non-empty**: exclusive membership of those ids plus tasks of any listed feature (unknown ids ignored). Do not also apply (b) or (c);
  (b) else, *section thread* on an **epic**: the epic plus only child features whose frontmatter `cites:` includes `{epic_id}#{section_slug}`;
  (c) else, *section thread* on a **feature**, or any *doc-level* thread: the commented doc and all its children.
  A root is a section thread iff stored `section` **as-is** equals `section_slug(h)` for some current `##` or deeper heading on that doc; otherwise it is doc-level (H1, `general`, unmatched, historical free-text). Do not re-slugify stored section on read. Section is never empty.
  Tasks inherit blocking from their parent feature. `blocking_threads_for(work_id)` loads roots from the work **and its ancestors** (parent feature, parent epic). Slugs come from one shared `cascade.comments.section_slug` (feat_016, dec_006). `WorkMeta.cites` is feature-tier only.

## Core dependencies

- feat_005 comment sidecar + `CommentPosted` queue delivery
- feat_012 plan viewer (`GET /plan/{id}`, `/api/doc/{id}`)
- feat_004 / feat_005 epic & feature `reply_comment`, graph boot
- feat_014 workspace / worktree doc resolution for reads
- feat_016 comment fields, parent-as-reply, `section_slug()`, View plan `#plan-comments` (completed 2026-10-20). HTTP kickoff is feat_020 (dec_012).
- feat_017 plan-viewer comment chrome (completed 2026-10-20). Gate must not consult chrome outdated state (dec_017).
- War Room `POST /api/comment` and `GET /api/comments/{doc_id}` (persist; board compose is a deep-link, feat_016)

## Feature breakdown

feat_016 and feat_017 are complete. **feat_019 planning started 2026-10-20** (dec_013, dec_017, dec_018). Remaining features stay in `docs/features/1_backlog/` until dispatch:

1. **[feat_016](../../features/3_completed/feat_016_comment_read_api_and_war_room_wiring.md) — Comment read API and War Room wiring** *(completed 2026-10-20; task_077–079 merged)* — GET `/api/comments/{doc_id}` and POST `/api/comment` carry `line_start` / `line_end` / `doc_sha` / `blocks`; `parent` is a reply (section inherited); `cascade.comments.section_slug()` is hyphenated GitHub-style. View plan deep-links to `/plan/{id}#plan-comments`. No second compose form. HTTP `kickoff_graph_queue_event` was **not** added (feat_016 D5 / dec_012); feat_020 owns delivery. Merge must keep one GET `/api/comments` handler. feat_016’s API table still shows a `kickoff` key; **that row is stale** — shipped POST is `202 {ok, comment_id}`.

2. **[feat_017](../../features/3_completed/feat_017_plan_viewer_comment_chrome.md) — Plan viewer comment chrome** *(completed 2026-10-20; task_080–082 merged)* — GitHub-style line threads on `/plan/{id}`: `data-src-line` from markdown source maps, gutter/selection compose, `parent` reply, render-only re-anchor / outdated, `#plan-comments [data-comment-id]` on each root. Blocking checkbox default off. Dropped the 3s poll. Resolve **status** only — the button is feat_018 (dec_007). POST 202 `{ok, comment_id}` — reload GET; no kickoff wait (dec_012, dec_015, dec_016). Gate (feat_019) must not read chrome outdated flags (dec_017).

3. **[feat_020](../../features/1_backlog/feat_020_agent_review_turns.md) — Agent review turns** — One `kickoff_turn(kind="comment")` per human CommentPosted / CommentReplied, including graphs with no prior chat. Watchdog delivers; HTTP enqueues only (do not add an HTTP eager turn — dec_012). Agent replies and `CommentResolved` do not loop. Playbook on existing `product_manager` skill.

4. **[feat_019](../../features/1_backlog/feat_019_scoped_dispatch_gates.md) — Scoped dispatch gates** *(planning 2026-10-20)* — One `cascade.comments.blocking_threads_for(work_id)` (work + ancestors, live worktree load) on human dispatch, Boss dispatch, `mint_task`, and feature/task integration merge. No bypass. Optional feature-tier `cites:` frontmatter. Does not gate `mint_feature` or `activate_epic`. May implement in parallel after feat_016; **must not merge before feat_018** (dec_013).

   **Planning lock (dec_017) — Feature Team honors this when minting tasks. Do not reopen epic decisions.**
   - Consume shipped feat_016 sidecar + `cascade.comments.section_slug`. Import; do not fork; do not import amendment/filename sluggers.
   - One function `blocking_threads_for(work_id)` is the product. Load open **blocking root** comments from the work and its ancestors (parent feature if a task, parent epic) via sidecar + `resolve_doc_worktree`. Replies never participate. Resolved and non-blocking roots never participate.
   - Do not read plan-viewer DOM, outdated flags, or line numbers. Outdated chrome is display-only (dec_016): an unmatched snippet still blocks if the root is blocking.
   - Membership is dec_003 on **stored** `section` / `blocks` plus **current worktree** `##+` headings. Unknown `blocks:` ids are ignored.
   - **Replace** (do not stack on) the existing `mint_task` “any blocking comment on this feature” check. Wire the same function into human War Room dispatch, Boss auto-dispatch, `mint_task`, and merge. No `force` flag. Do not gate `mint_feature` or `activate_epic`.
   - Closeout rollup is unchanged: any open human thread still blocks complete. Do not fold closeout into this function.
   - Add optional `WorkMeta.cites: list[str]` as `{epic_id}#{section_slug}` (already hyphenated). Do not infer cites from spec prose. Missing cites is the known limitation (dec_003). Cites that match no current heading are **warnings** on the refusal, not silent and not a hard fail.
   - Backfill `cites:` on epic_002’s children from the cites already listed in those spec bodies so rule (b) is testable.
   - Refusal lists thread id, `doc_id`, section, and a `/plan/{doc_id}#plan-comments` link.
   - **Must not merge or close out before feat_018** (dec_013). Implementation may proceed; `depends_on` stays feat_016.
   - **Out of this feature:** Resolve button (feat_018), chrome (feat_017 shipped), agent kickoff (feat_020), `blocks:` picker, cite inference, `force` flag, second slugger, gating `activate_epic` / `mint_feature`, changing closeout, sidecar rewrite.
   - Suggested task slice (Feature Team mints; do not grow past this): (1) `cites:` + `blocking_threads_for` membership tests; (2) four call sites + replace `mint_task` check + refusal payload. High-signal tests are dispatch / `mint_task` / merge API tests (epic-section + cites hit/miss, feature-section blocks tasks, doc-level blocks all children, `blocks:` override, ancestor scan, non-blocking/resolved do not refuse, Boss path equals human). Not a unit mock of `section_slug`.

   **Architect lock (dec_018) — honor this when minting. Do not reopen epic decisions.**
   - Home: `cascade.comments.blocking_threads_for`. Import it from War Room dispatch, Boss auto-dispatch, `mint_task`, and feature/task integration merge. Do not put a second copy in HTTP-only code or in JS.
   - Live load every call through `resolve_doc_worktree` for each ancestor doc (epic sidecar in the epic worktree; feature sidecar and `cites:` in the feature worktree). No graph-boot cache: a human resolve must unblock the next dispatch in the same process.
   - Pure function: return the in-scope blocking roots (empty = allow). No writes, no queue events, no sidecar rewrite, no kickoff.
   - `WorkMeta.cites` is optional and **feature-tier only**. Gate reads frontmatter only. Backfill epic_002 children from body cites already listed; do not infer at runtime from the "Cites (promote..." prose.
   - `blocks:` non-empty is exclusive (listed ids + tasks of listed features). Empty/absent falls through to (b)/(c).
   - Compare stored `section` as-is to live `section_slug(##+)` headings. Do not re-slugify historical free-text (`Open questions` stays doc-level). No heading snapshot. No fuzzy rename match. Renamed heading → unmatched → doc-level (broader), accepted.
   - `mint_task(feature_id)` calls `blocking_threads_for(feature_id)`. `dispatch_task` / merge of a task call `blocking_threads_for(task_id)` (ancestor scan + inherit).
   - Merge = existing feature/task integration merge of that `work_id`. Not `git commit`, not closeout rollup.
   - Refusal reuses the existing War Room/Boss refusal shape (not 500). Unmatched-cite warnings ride along and never refuse by themselves.
   - Extra test cases on the same slice: sibling feature without matching `cites:` is allowed; resolve then dispatch in-process succeeds; historical free-text section classifies as doc-level.

5. **[feat_018](../../features/1_backlog/feat_018_human_resolve_and_audit.md) — Human resolve and audit** — POST `/api/comment/resolve` on an open root only; cascades to descendants; agents cannot resolve; resolved rows stay in JSONL; Resolve control binds to `#plan-comments [data-comment-id]`; `In reply to: cmt_NNN` in the decision log. Spec `depends_on` is feat_016 only (dec_014); dispatch even if YAML still lists feat_017. Chrome has shipped, so the `data-comment-id` marker is already on the list.

**Remaining dispatch (human or Boss):** feat_017 is complete — do not re-dispatch it. feat_019 is in planning — do not re-dispatch it. **Dispatch feat_018 now** (dec_007, dec_013, dec_014): YAML may still list `depends_on: feat_017`; ignore that, chrome is done, and feat_019 closeout waits on the resolve guard. feat_020 can start now.

## Open questions

_(none — all resolved, see Decision log dec_001–dec_018)_

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
  Chose feat_019 Feature Team mints only gate tasks against the locked scope (dec_003/004/008/010) and merge wait (dec_013). One function blocking_threads_for(work_id) is the entire product: (1) Load open blocking root comments from the work and its ancestors (parent feature if a task, parent epic) via the existing sidecar + resolve_doc_worktree. Do not read plan-viewer DOM, outdated flags, or line numbers. Replies never participate; resolved and non-blocking roots never participate. (2) Membership uses dec_003 precedence on stored section/blocks plus current worktree ##+ headings via imported cascade.comments.section_slug — do not fork it. Outdated chrome is display-only (dec_016): an unmatched snippet still blocks if the root is blocking. (3) Replace (do not stack on) the existing mint_task "any blocking comment on this feature" check. Wire the same function into human War Room dispatch, Boss auto-dispatch, mint_task, and merge. No force flag, no second code path. Do not gate mint_feature or activate_epic. Closeout rollup is unchanged (any open human thread still blocks complete) — do not fold closeout into this function. (4) Add optional WorkMeta.cites: list[str] as {epic_id}#{section_slug}, already hyphenated. Do not infer cites from spec prose. Missing cites is the known limitation (dec_003). Cites that match no current heading are warnings on the refusal, not silent and not a hard fail. Backfill cites: on epic_002's children from the cites already listed in those spec bodies so rule (b) is testable. (5) Refusal lists thread id, doc_id, section, and a /plan/{doc_id}#plan-comments link. Unknown blocks: ids are ignored. (6) Must not merge or close out before feat_018's agent-tool resolve denial is on the board (dec_013). Implementation may proceed; depends_on stays feat_016. Out of this feature: Resolve button (feat_018), chrome (feat_017 shipped), agent kickoff (feat_020), blocks picker, cite inference, force flag, second slugger, gating activate_epic/mint_feature, changing closeout, sidecar rewrite. Suggested slice: (1) cites: + blocking_threads_for membership tests; (2) four call sites + replace mint_task check + refusal payload. High-signal tests are dispatch/mint_task/merge API tests (epic-section + cites hit/miss, feature-section blocks tasks, doc-level blocks all children, blocks: override, ancestor scan, non-blocking/resolved do not refuse, Boss path equals human). Not a unit mock of section_slug..
  Rationale: FeaturePlanningStarted for feat_019 after feat_017 closeout. The remaining holes are stacking the old mint_task any-blocking rule (stricter than dec_003), missing Boss or merge (the leak dec_004 forbids), gating closeout or mint_feature/activate_epic, skipping outdated threads, inferring cites from prose, or merging before feat_018. Locking the store-side consumer contract keeps operator success #3 the smallest slice and stops a race with feat_018.
  Honors: dec_003, dec_004, dec_006, dec_008, dec_010, dec_013, dec_016; feat_016 shipped sidecar and section_slug; Intent operator success #3 (unresolved blocking threads stop dispatch/merge); explicit cuts (no force flag, no cite inference, blocks API-only, no gating mint_feature/activate_epic); FeaturePlanningStarted feat_019.

- `dec_018` · 2026-10-20 · Epic Architect · **feat_019 planning — call-site and worktree seam**
  Chose blocking_threads_for as a pure Python function next to the comment store (cascade.comments.blocking_threads_for), imported by every mutating call site — not a War Room HTTP helper, not JS, not a second copy in Boss. Each call live-loads ancestor sidecars and feature cites through resolve_doc_worktree (never trunk pointers, never a boot-time cache, never plan-viewer JS). WorkMeta.cites is optional and feature-tier only; the gate reads frontmatter only (no prose inference); backfill epic_002 children from the cites already listed in those spec bodies. blocks: non-empty is an exclusive membership set (listed ids plus tasks of listed features); do not union with (b)/(c). Compare stored section as-is to live section_slug(##+) headings — do not re-slugify historical free-text; unmatched is doc-level (dec_008), no heading snapshot, no fuzzy rename match. mint_task(feature_id) gates on blocking_threads_for(feature_id); dispatch_task/merge of a task gate on the task id (ancestor scan + inherit). Merge means the existing feature/task integration merge for that work_id, not git commit and not closeout rollup. Return the in-scope blocking roots; empty means allow. Call sites reuse the existing War Room/Boss refusal shape (not 500); payload lists thread id, doc_id, section, /plan/{doc_id}#plan-comments; unmatched-cite warnings ride along and never refuse by themselves. No writes, queue events, or sidecar rewrites. Must not merge before feat_018 (dec_013). Out of this feature unchanged.
  Rationale: FeaturePlanningStarted for feat_019. dec_017 locked the store-side consumer contract. Remaining holes: putting the gate in War Room HTTP only (Boss/merge would bypass), caching comments at graph boot (resolve would not unblock in-process), reading trunk pointer specs/sidecars (dec_005), inferring cites from the 'Cites (promote...' body line at runtime, unioning blocks: with section scope, re-slugifying historical 'Open questions' rows or snapshotting headings to preserve rule (b) after a rename, or gating closeout/git commit. Locking the call-site/worktree seam keeps operator success #3 the smallest slice and stops a leak of the human gate.
  Honors: dec_003, dec_004, dec_005, dec_008, dec_010, dec_013, dec_017; feat_016 shipped sidecar, section_slug, resolve_doc_worktree; Intent operator success #3; Filesystem is truth; stacked worktrees / pointer epics; Dispatch law unchanged; FeaturePlanningStarted feat_019.

- `dec_019` · 2026-10-20 · Epic Manager · **feat_019 closeout — gate shipped ahead of resolve**
  Chose Accept feat_019 closeout (task_083–085): cascade.comments.blocking_threads_for live-loads work+ancestors via sidecar + resolve_doc_worktree, is imported by human/Boss dispatch, mint_task (replacing the old any-blocking-comment check), and feature/task integration merge, with no force flag. WorkMeta.cites is optional and feature-tier only. Do not reopen or roll back the gate. Sequencing vs dec_013 was missed: feat_019 closed while feat_018 is still active, so agent resolve_comment still exists on the gated tree until feat_018 merges. feat_018 task_086 already implements the store+tool guard; merging feat_018 is the leak close, not a new gate task. cites: were not copied onto epic_002 children frontmatter; keep the known missing-cites limitation (dec_003) rather than minting a backfill task — Feature Teams copy the body cites line into YAML on their next spec edit..
  Rationale: FeatureCompleted for feat_019. The shipped function and four call sites meet operator success #3 and dec_017/dec_018. Rolling the gate back would cut a working human gate to wait on chrome/resolve process order. The remaining hole is agent resolve_comment on that tree, which is already feat_018's job (task_086 done, task_087 in flight). A cites linter or backfill feature would be gold-plating of a limitation we already accepted.
  Honors: dec_003, dec_004, dec_005, dec_006, dec_008, dec_010, dec_013, dec_017, dec_018; feat_016 shipped sidecar and section_slug; Intent operator success #3; explicit cuts (no force flag, no cite inference, no gating mint_feature/activate_epic); FeatureCompleted feat_019.

- `dec_020` · 2026-10-20 · Epic Manager · **feat_018 planning — human resolve is the leak close**
  Chose feat_018 Feature Team finishes only the remaining resolve slice against shipped chrome and the already-landed store guard. task_086 is done: resolve_comment requires author=human, cascades root+descendants, refuses non-roots, copies feat_016 fields on rewrite, and is unregistered from epic/feature tools. task_087 is the rest: POST /api/comment/resolve {doc_id, comment_id} with author forced to human — 202 {ok, comment_id}, 404 missing, 400 NotARoot on a reply, idempotent 202 on an already-resolved root; no kickoff_graph_queue_event or kickoff_turn. Resolve button on each open root in #plan-comments [data-comment-id]; none on replies or resolved roots; click then reload GET. Chrome has shipped (feat_017): mount inside the existing list render; do not add a second panel, poll, or WYSIWYG. Recreating the button on chrome's existing re-render is OK; do not re-register resolve_comment on agent tools. Do not re-implement blocking_threads_for. Merge of this feature is what closes the dec_013 leak on the gated tree. YAML may still list depends_on: feat_017; ignore it (dec_014). Out: unresolve, hide-resolved, second auth layer, comment polling, gates, HTTP eager turn, blocks picker, a new cites-backfill task..
  Rationale: feat_018 is active with task_087 in flight after feat_019 closeout. The hole is gold-plating resolve (unresolve, poll, a second list) or re-opening the gate, which would delay the human click that operator success #3 now depends on. Locking the remaining slice keeps resolve the smallest un-bypass of the shipped gate.
  Honors: dec_007, dec_009, dec_011, dec_013, dec_014, feat_016 shipped POST/GET, feat_017 shipped data-comment-id chrome, feat_018 D1–D6, Intent (resolved only as human), Feature active feat_018.
## Amendment log

_(none)_
