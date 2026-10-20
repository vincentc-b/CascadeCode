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
  ├─ inline / section anchors + thread UI  [feat_017]
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

Dispatch law + new scope gates (feat_019)
  ├─ blocking_threads_for scans the work + ancestors; refuse dispatch/mint_task/merge
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
- **Blocking is human-only** on create (existing store rule). Agents may reply but not resolve or set blocking.
- **Scope (locked, see dec_003/dec_004/dec_008/dec_010):** affected work for an open blocking *root* thread, in order of precedence:
  (a) explicit `blocks: [work_id, …]` on the root comment, if present (unknown ids ignored);
  (b) else, *section thread* on an **epic**: the epic plus only child features whose frontmatter `cites:` includes `{epic_id}#{section_slug}`;
  (c) else, *section thread* on a **feature**, or any *doc-level* thread: the commented doc and all its children.
  A root is a section thread iff `section` matches a current `##` or deeper heading on that doc (`section_slug`); otherwise it is doc-level (H1, `general`, unmatched). Section is never empty.
  Tasks inherit blocking from their parent feature. `blocking_threads_for(work_id)` loads roots from the work **and its ancestors** (parent feature, parent epic). Slugs come from one shared `cascade.comments.section_slug` (feat_016, dec_006).

## Core dependencies

- feat_005 comment sidecar + `CommentPosted` queue delivery
- feat_012 plan viewer (`GET /plan/{id}`, `/api/doc/{id}`)
- feat_004 / feat_005 epic & feature `reply_comment`, graph boot
- feat_014 workspace / worktree doc resolution for reads
- feat_016 comment fields, parent-as-reply, `section_slug()`, View plan `#plan-comments` (completed 2026-10-20). HTTP kickoff is feat_020 (dec_012).
- War Room `POST /api/comment` and `GET /api/comments/{doc_id}` (persist; board compose is a deep-link, feat_016)

## Feature breakdown

feat_016 is complete. Remaining features stay in `docs/features/1_backlog/` until dispatch:

1. **[feat_016](../../features/3_completed/feat_016_comment_read_api_and_war_room_wiring.md) — Comment read API and War Room wiring** *(completed 2026-10-20; task_077–079 merged)* — GET `/api/comments/{doc_id}` and POST `/api/comment` carry `line_start` / `line_end` / `doc_sha` / `blocks`; `parent` is a reply (section inherited); `cascade.comments.section_slug()` is hyphenated GitHub-style. View plan deep-links to `/plan/{id}#plan-comments`. No second compose form. HTTP `kickoff_graph_queue_event` was **not** added (feat_016 D5 / dec_012); feat_020 owns delivery. Merge must keep one GET `/api/comments` handler.

2. **[feat_017](../../features/1_backlog/feat_017_plan_viewer_comment_chrome.md) — Plan viewer comment chrome** — Line-level threads on `/plan/{id}`: `data-src-line`, gutter "+" or text selection, re-anchor / outdated, blocking checkbox default off. In-thread human reply via `parent`. Resolve **status** only; the button is feat_018 (dec_007).

3. **[feat_020](../../features/1_backlog/feat_020_agent_review_turns.md) — Agent review turns** — One `kickoff_turn(kind="comment")` per human CommentPosted / CommentReplied, including graphs with no prior chat. Watchdog delivers; HTTP enqueues only (do not add an HTTP eager turn — dec_012). Agent replies and `CommentResolved` do not loop. Playbook on existing `product_manager` skill.

4. **[feat_019](../../features/1_backlog/feat_019_scoped_dispatch_gates.md) — Scoped dispatch gates** — One `blocking_threads_for(work_id)` (work + ancestors) on human dispatch, Boss dispatch, `mint_task`, and merge. No bypass. Optional feature `cites:` frontmatter. Does not gate `mint_feature` or `activate_epic`.

5. **[feat_018](../../features/1_backlog/feat_018_human_resolve_and_audit.md) — Human resolve and audit** — POST `/api/comment/resolve` on an open root only; cascades to descendants; agents cannot resolve; resolved rows stay in JSONL; Resolve control on the plan thread list; `In reply to: cmt_NNN` in the decision log.

**Remaining dispatch (human or Boss):** feat_017 and feat_018 in the same wave (dec_007). feat_020 and feat_019 can start now (both depend only on completed feat_016). Suggested order: 017+018 first (operator can leave and resolve threads), then 020 (agent replies), 019 (gates) overlapping if capacity allows.

## Open questions

_(none — all resolved, see Decision log dec_001–dec_012)_

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

## Amendment log

_(none)_
