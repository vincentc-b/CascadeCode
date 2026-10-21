---
id: epic_002
title: Plan-view review threads
tier: epic
status: completed
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

Watchdog deliver_queue_kickoffs → kickoff_turn(kind="comment") for human authors (feat_020 shipped, task_088–089)
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
- **Kickoff edges only:** Posting a comment enqueues `CommentPosted`; one agent turn is delivered by the watchdog — no timer polling for “new comments on main.” HTTP POST does not start a turn (dec_011, dec_012, dec_021–dec_025, dec_027). Resolve POST also does not start a turn (dec_011, dec_020). Do not add HTTP `kickoff_graph_queue_event` to “fix” cold start. **feat_016 D4/D5 “keep HTTP kickoff at merge” is void (dec_027)** — do not treat that completed spec as the live contract. Filter lives inside existing `deliver_queue_kickoffs`; skipped events still advance the offset (dec_023). `kickoff_turn` returns like live chat — do not wait for `reply_comment` (dec_025).
- **Stacked worktrees:** Comment sidecars for an active epic/feature live in the same git root as that team’s plan (`resolve_doc_worktree` / existing comment repo rules). A comment `kickoff_turn` uses that same worktree as the graph workspace (dec_005, dec_023); trunk pointers never get a sidecar.
- **Read-only plan renderer** may gain comment *chrome*; plan body edits still go through agent tools or git, not WYSIWYG in the viewer (feat_012 read-only stance unless explicitly extended).
- **Comment chrome is render-only (dec_016).** `line_start` / `line_end` are 1-based markdown source lines from the renderer token source map. Re-anchor and outdated never rewrite the sidecar. `#plan-comments` is upserted by `data-comment-id`, never replaced via `innerHTML`. Task-tier GET `/api/comments` 400 stays. **feat_017 shipped this** (task_080–082). **feat_018 shipped the Resolve button** on that list; do not add a second panel.
- **Blocking is human-only** on create (existing store rule). Agents may reply but not resolve or set blocking. feat_018 shipped the store+tool guard and the Resolve button; `resolve_comment` is unregistered. The dec_013 leak is closed. feat_020 must not re-register the tool (task_088–089 did not).
- **Comment turns are watchdog-only (dec_011, dec_012, dec_021–dec_025, dec_027). feat_020 shipped this** (task_088–089). Filter lives inside existing `deliver_queue_kickoffs` (not a second subscriber). It starts `kickoff_turn(kind="comment")` only for human `CommentPosted` / `CommentReplied`. Agent replies and `CommentResolved` ingest the queue offset and do not start a turn; skipped events must still advance the cursor. Offset is exactly-once — no `kicked_off` sidecar flag. One turn per matching event, owning graph only (`epic_{id}` / `feat_{id}` from `doc_id`); do not fan-out to parent epic, child features, or iterate owners/roles. Empty or never-attached graphs still boot **the same way War Room attach does**: same roster/skills/tools (`resolve_comment` stays unregistered; existing `reply_comment` stays registered), workspace `resolve_doc_worktree(doc_id)` — never trunk, never a throwaway worktree, never a headless comment runner. `kind="comment"` is a KickoffReason tag only; the turn path is the existing planning turn (same speaker selection as live chat). Author filter is the event/sidecar `author` field (`human` only). `KickoffReason.message` is `{role: "human", content: ...}` with the **shipped** feat_020-spec shape `cmt_NNN on {doc_id} #{section} [blocking]\n{body}` (dec_027; dec_024/025 four-line prefix is planning history). Playbook is one short section on the existing `product_manager` skill (loaded by that boot, not injected as a system prompt, not copied onto architect skills). Always `reply_comment` in-thread with the existing tool `comment_id` = the triggering comment id (dec_024, dec_025); a spec/decision edit is not a substitute. `write_doc` remains optional. No comment-failure toast/spinner. No HTTP eager turn, no generic `queue_event` kickoff, no comment-only role, no digest/batch, no second writer, no poll/spinner for the agent reply. If `kickoff_turn` raises, keep the event (existing watchdog retry).
- **Comment reply write-path (dec_025, shipped).** `deliver_queue_kickoffs` and `kickoff_turn` never call `reply_comment` and never append the sidecar (no auto-ack). The in-thread reply is only the existing feat_004/005 `reply_comment(comment_id, body)` tool during the existing planning turn — `comment_id` is the parent (the triggering event’s comment id, not the thread root and not the human row’s parent). Do not add a `parent` kwarg, a `review_comment` facade, or a second reply tool. Agents never POST `/api/comment` (that route is always `author=human` and would loop). Stored author is the speaking role already in the feat_016 enum (`epic_manager` / `feature_lead` / …), never `human`, never a new `comment-reviewer`. `kickoff_turn` returns like live chat; offset advances when kickoff is accepted, not when a sidecar reply appears. Do not skip a turn because the thread was resolved before the agent spoke; do not un-resolve. Restore the existing `reply_comment` registration if missing; do not add a `kind="comment"` allowlist.
- **Gate is store-only and shipped (dec_017, dec_018, dec_019).** `cascade.comments.blocking_threads_for(work_id)` is a pure function next to the comment store. Each call live-loads open blocking roots from the work and ancestors via sidecar + `resolve_doc_worktree` (never trunk pointers, never a boot-time cache, never plan-viewer JS). It reads current worktree `##+` headings. It does not consult outdated state, line numbers, or rewrite comments. Replaced the existing `mint_task` any-blocking check; do not stack it back. Do not gate `mint_feature` or `activate_epic`. Closeout rollup stays separate. Merge means the existing feature/task integration merge for that `work_id`, not git commit. Do not re-implement the gate.
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
- feat_016 comment fields, parent-as-reply, `section_slug()`, View plan `#plan-comments` (completed 2026-10-20). HTTP kickoff stayed out (dec_012, dec_021, dec_027). feat_016 D4/D5 merge note is void.
- feat_017 plan-viewer comment chrome (completed 2026-10-20). Gate must not consult chrome outdated state (dec_017).
- feat_018 human resolve and audit (completed 2026-10-20). Agent `resolve_comment` is unregistered; the dec_013 leak is closed.
- feat_019 scoped dispatch gates (completed 2026-10-20; task_083–085). Do not reopen the gate.
- feat_020 agent review turns (completed 2026-10-20; task_088–089). Watchdog-only `kind=comment` kickoff + `product_manager` playbook. Architect closeout holds (dec_027).
- War Room `POST /api/comment` and `GET /api/comments/{doc_id}` (persist; board compose is a deep-link, feat_016)

## Feature breakdown

**All five features are complete.** Architect closeout holds (`dec_027`). I have not minted a sixth feature. Epic closeout is human-only — ready for your review.

1. **[feat_016](../../features/3_completed/feat_016_comment_read_api_and_war_room_wiring.md) — Comment read API and War Room wiring** *(completed 2026-10-20; task_077–079 merged)* — GET `/api/comments/{doc_id}` and POST `/api/comment` carry `line_start` / `line_end` / `doc_sha` / `blocks`; `parent` is a reply (section inherited); `cascade.comments.section_slug()` is hyphenated GitHub-style. View plan deep-links to `/plan/{id}#plan-comments`. No second compose form. HTTP `kickoff_graph_queue_event` was **not** added (feat_016 D5 / dec_012). **feat_016 D4/D5 “keep HTTP kickoff at merge” is void (dec_027).** If a later merge reintroduces that call or a `kickoff` key, delete it. Merge must keep one GET `/api/comments` handler. feat_016’s API table still shows a `kickoff` key; **that row is stale** — shipped POST is `202 {ok, comment_id}`.

2. **[feat_017](../../features/3_completed/feat_017_plan_viewer_comment_chrome.md) — Plan viewer comment chrome** *(completed 2026-10-20; task_080–082 merged)* — GitHub-style line threads on `/plan/{id}`: `data-src-line` from markdown source maps, gutter/selection compose, `parent` reply, render-only re-anchor / outdated, `#plan-comments [data-comment-id]` on each root. Blocking checkbox default off. Dropped the 3s poll. Resolve **status** only — the button is feat_018 (dec_007, shipped). POST 202 `{ok, comment_id}` — reload GET; no kickoff wait (dec_012, dec_015, dec_016). Gate (feat_019 shipped) must not read chrome outdated flags (dec_017).

3. **[feat_020](../../features/3_completed/feat_020_agent_review_turns.md) — Agent review turns** *(completed 2026-10-20; task_088–089 merged)* — One `kickoff_turn(kind="comment")` per human CommentPosted / CommentReplied, including graphs with no prior chat. Watchdog delivers; HTTP enqueues only. Agent replies and `CommentResolved` ingest the offset and do not loop. Playbook on existing `product_manager` skill. Mint locks were dec_021–dec_025; closeout accepted as dec_026; architect lock is dec_027.

   **What shipped (task_088 + task_089):**
   - Shared human-comment kickoff inside existing `deliver_queue_kickoffs`; HTTP POST stays `202 {ok, comment_id}` with no `kickoff` key. Strip `kickoff_graph_queue_event` on that route if it was reintroduced (dec_027).
   - One turn on the owning graph only. Empty / never-attached graphs boot like War Room attach into `resolve_doc_worktree`. Task-tier stays 400. No parent/child fan-out. No second subscriber, comment watchdog, or `kind=comment` tool allowlist.
   - In-thread reply is the existing `reply_comment(comment_id, body)` during the existing planning turn. Watchdog and `kickoff_turn` never write the sidecar (no auto-ack).
   - Playbook is a short section on `skills/roles/product_manager/SKILL.md` only. Do not add a skill, role, or graph.

   **Do not reopen.** Planning locks stay in dec_021–dec_025. Shipped KickoffReason content is `cmt_NNN on {doc_id} #{section} [blocking]\n{body}` — that is the implementation contract (dec_027). dec_024/025 four-line prefix and four playbook rules stay planning history. `comment_id` is the leading `cmt_NNN`; `reply_comment(comment_id, body)` parents on the triggering event. No sixth feature to reformat it.

4. **[feat_019](../../features/3_completed/feat_019_scoped_dispatch_gates.md) — Scoped dispatch gates** *(completed 2026-10-20; task_083–085 merged)* — One `cascade.comments.blocking_threads_for(work_id)` (work + ancestors, live worktree load) on human dispatch, Boss dispatch, `mint_task`, and feature/task integration merge. No bypass. Optional feature-tier `cites:` frontmatter. Does not gate `mint_feature` or `activate_epic`. Closed before feat_018 (dec_013 miss, accepted as dec_019); **feat_018 has now shipped**, so agent `resolve_comment` is unregistered and the leak is closed. Do not reopen the gate. Body cites on epic_002 children were not promoted to frontmatter; missing `cites:` stays the known limitation (dec_003).

5. **[feat_018](../../features/3_completed/feat_018_human_resolve_and_audit.md) — Human resolve and audit** *(completed 2026-10-20; task_086–087 merged)* — POST `/api/comment/resolve` on an open root only; cascades to descendants; agents cannot resolve; resolved rows stay in JSONL; Resolve control binds to `#plan-comments [data-comment-id]`. Human-only resolve shipped; `resolve_comment` is unregistered; the dec_013 leak on the gated tree is closed.

**Remaining dispatch (human or Boss):** none. feat_016, feat_017, feat_018, feat_019, and feat_020 are complete — do not re-dispatch them. Do not mint another feature. **Epic closeout is yours** (human-only). Architect review is done (`dec_027`).

**Cuts still explicit:** no second War Room compose pane, no `force` flag, no gating `mint_feature` / `activate_epic`, `blocks:` API-only, missing `cites:` is a known limitation, no comment polling, no comment-only role, no required spec edit on every comment (an in-thread reply meets success #2; a spec edit is not a substitute), no comment watchdog, no trunk sidecar, no second tool allowlist, no spec-only comment turn, no new-root reply, no comment-failure toast/spinner, no playbook copy onto architect skills, no watchdog auto-reply, no agent HTTP compose, no new comment author, no wait-for-reply inside the watchdog, no new reply tool/facade, no sixth feature to reformat the KickoffReason prefix, no following feat_016 D4/D5 to put HTTP kickoff back.

## Open questions

_(none — all resolved, see Decision log dec_001–dec_027)_

## Decision log

The 27 decisions remain on the epic as previously recorded: `dec_001` through `dec_027` (see prior board revision `c6578567a21255af0e6ce5a92579a7734a6e6c5b` and `record_decision` output). Do not reconstruct `dec_001`–`dec_024` from chat (dec_027).

- `dec_001` through `dec_024` remain as recorded on the prior board revision `c6578567a21255af0e6ce5a92579a7734a6e6c5b`.

- `dec_025` · 2026-10-20 · Epic Architect · **feat_020 planning — reply write-path and test seam**
  Chose feat_020 Feature Team mints only the existing two-task slice against dec_021–dec_024 plus this write-path lock. deliver_queue_kickoffs and kickoff_turn never call reply_comment and never append the sidecar (no auto-ack). The in-thread reply is only the existing feat_004/005 reply_comment(comment_id, body) during the existing planning turn; comment_id is the parent (the triggering event’s comment id). Agents never POST /api/comment (author is always human on that route). Stored author is the speaking role already in the feat_016 enum, never human, never a new comment-reviewer. KickoffReason.message stays {role: "human", content: ...}; content is the only channel the model sees and uses a stable prefix (comment_id, section, blocking, parent line only if the human row is a reply) then a blank line then the human body verbatim — no extra KickoffReason fields, no sidecar dump. kickoff_turn returns like live chat; offset advances when kickoff is accepted, not when a sidecar reply appears. Do not skip a matching human event because the thread is already resolved; reply_comment stays allowed on a resolved thread; the agent does not un-resolve. Restore the existing reply_comment registration if missing; do not add a kind=comment allowlist. Tests: (1) POST then deliver_queue_kickoffs spies one kickoff_turn(kind="comment") with that content prefix (mock kickoff_turn; no LLM); (2) direct agent-role reply_comment writes the worktree sidecar and GET sees parent=human_id and author≠human; (3) SKILL.md contains-check (dec_024); (4) a POST→watchdog→sidecar-reply path is allowed only if the suite already has a scripted/stub planning model — do not add a harness, recorded fixture, headless runner, or watchdog auto-ack to satisfy dec_024’s “yields a sidecar reply” wording.
  Rationale: feat_020 is in planning. dec_024 required an in-thread sidecar reply and a POST→watchdog test that “yields” that reply, while dec_022 forbids unit-testing the LLM and dec_023 forbids a headless runner. The remaining holes that would ship the wrong reply: the watchdog writing an auto-ack so the test passes without an agent turn; the agent POSTing /api/comment (author=human, starts another turn); comment_id buried in prose or a KickoffReason field the transcript drops so the playbook cannot set parent; kickoff_turn waiting for reply_comment and stalling the queue; skipping a turn after the human resolves; or a new reply tool / comment-reviewer author / kind=comment allowlist that reopens the resolve leak. Locking the write-path and test seam keeps operator success #2 the existing planning turn plus the existing reply_comment tool.
  Honors: dec_012, dec_016, dec_021, dec_022, dec_023, dec_024, dec_005, dec_020; feat_016 enqueue-only POST {ok, comment_id} with author always human and existing reply_comment inherit; feat_017 no-poll chrome; feat_018 human-only resolve (tool unregistered); Intent operator success #2; Kickoff edges only; stacked worktrees / pointer epics; Filesystem is truth; FeaturePlanningStarted feat_020.

- `dec_026` · 2026-10-20 · Epic Manager · **feat_020 closeout / epic readiness**
  Chose Accept feat_020 closeout (task_088 watchdog kickoff + HTTP enqueue-only; task_089 product_manager playbook). All five features are complete. Do not mint a sixth feature. Do not re-dispatch. Epic stays active until the human closes it. Known leftovers accepted: (1) feat_020 spec still documents the older KickoffReason content shape `cmt_NNN on {doc_id} #{section} [blocking]` and a five-bullet playbook versus dec_024/025's four-line prefix and four playbook rules — comment_id is in content either way; reformatting is negative ROI; (2) epic_002 children still record cites in spec body, not frontmatter (dec_019); (3) feat_016 API table still shows a stale kickoff key.
  Rationale: Operator success 1–4 are covered by shipped feat_016–020: compose on the plan page, in-thread owning-team reply via watchdog, human-only resolve, and scoped dispatch/merge gates. A sixth feature to reformat the kickoff prefix or backfill cites would not move those criteria. Feature worktrees are denied to this graph; closeout evidence is the completed feat_020 copy (status=completed, children task_088/task_089) and read_doc resolving under 3_completed. The two-task slice matches the locked mint plan. Cuts stay explicit.
  Honors: dec_012, dec_013, dec_019, dec_021, dec_022, dec_023, dec_024, dec_025, dec_003, Intent operator success 1-4, FeatureCompleted feat_016/017/018/019/020, Kickoff edges only, no force flag, no second War Room compose, no comment-only role, no cites backfill, human-only epic closeout.

- `dec_027` · 2026-10-20 · Epic Architect · **feat_020 closeout / epic readiness — architect lock**
  Chose Accept feat_020 closeout and the five-feature epic as ready for human closeout. Do not mint a sixth feature. Do not re-dispatch feat_016–020. feat_016 D4/D5 "keep HTTP kickoff_graph_queue_event at merge" is void — superseded by dec_012 and shipped feat_020 (POST /api/comment stays 202 {ok, comment_id}, no kickoff key). If a later merge reintroduces that call or a kickoff key, delete it; do not treat the completed feat_016 spec as the live contract. The shipped KickoffReason content shape `cmt_NNN on {doc_id} #{section} [blocking]\n{body}` is the implementation contract; dec_024/025's four-line prefix stays planning history. comment_id is the leading cmt_NNN; reply_comment(comment_id, body) still parents on the triggering event. Do not reformat the prefix or playbook. Do not reconstruct the collapsed dec_001–dec_024 log. Epic stays active until the human closes it.
  Rationale: Holistic review of the five completed specs (epic worktree copies; feature worktrees denied to this graph). Operator success 1–4 each have one owner: 016+017 compose, 020 in-thread turn, 018 human resolve, 019 store-side gate. The remaining hole that would double-fire a turn or skip the watchdog is a future reader following feat_016's merge note and putting kickoff back on HTTP. Voiding that note is cheaper than a sixth feature. Prefix/playbook drift is documentation, not a missing seam: the tool API is still reply_comment(comment_id) and agents still cannot resolve, dispatch, or set blocking. Reconstructing 24 decision entries from chat would invent text.
  Honors: dec_012, dec_013, dec_019, dec_021, dec_022, dec_023, dec_024, dec_025, dec_026, dec_003, dec_004, dec_005, Intent operator success 1-4, FeatureCompleted feat_016/017/018/019/020, Kickoff edges only, no force flag, no second War Room compose, no comment-only role, no HTTP eager turn, human-only epic closeout, Filesystem is truth, stacked worktrees.

## Amendment log

_(none)_
