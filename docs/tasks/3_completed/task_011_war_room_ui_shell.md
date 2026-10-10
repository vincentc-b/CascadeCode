---
id: task_011
title: Server-rendered War Room UI shell
tier: task
status: completed
parent: feat_003
children: []
depends_on:
- task_009
- task_010
owners:
- swe
skills: []
parent_rev: null
created: '2026-10-09'
updated: '2026-10-10'
---

# Server-rendered War Room UI shell

## Parent Feature

[feat_003](../../features/2_active/feat_003_local_war_room.md) — Local War Room UI.

## Depends on

- [task_009](../../tasks/3_completed/task_009_human_dispatch_routes.md) (human dispatch POST routes)
- [task_010](../../tasks/3_completed/task_010_transcript_toasts_sidecar.md) (chat, toasts, attach)

## Acceptance criteria

- **Default home** (`GET /` or dedicated `GET /war-room`) is **server-rendered HTML** (stdlib templates: e.g. `string.Template`, manual format, or minimal template helper — **no Jinja dependency unless already in repo**) showing on one view:
  - **Epic War Room chat** pane (messages from `GET /api/chat/{active_epic_graph_id}`; compose form POSTs to chat API when Epic graph is attached).
  - **Board columns** (Epics / Features / Tasks) populated from `GET /api/board` data embedded or fetched client-side via same-origin fetch from static JS allowed).
  - **Toast stream** polling `GET /api/toasts?after=` and rendering new toasts.
- **Human controls** visible on board rows: buttons/forms that call **`POST /api/activate_epic`**, **`POST /api/dispatch_feature`**, **`POST /api/dispatch_task`** (human only); optional **Ask Boss to dispatch** triggers task_009 ask-boss route; display `DispatchResult.reason` on failure.
- **Attach/detach chrome**: UI to attach to a Feature (or Epic) from the board; Feature room may be a **placeholder panel** ("Feature room — full drop-in in feat_005") when attached; detaching returns focus to Epic War Room default.
- **Amendment pane**: present as **closed stub** (collapsible or disabled panel labeled stub until feat_006; no accept/reject actions).
- **Comment thread chrome**: section showing placeholder copy that **comment storage is feat_005**; includes a **human-only `blocking` toggle** in the UI (checkbox) that is **chrome only** — toggling does not write `docs/_comments/` unless feat_005 exists (label must say "UI stub — no persistence yet").
- **Task rows**: **no chat room** for Tasks; show local branch name **`task/{task_id}`** (literal pattern) and a **Merge** button posting to **`POST /api/merge_task_branch`** (expects 202 stub from task_009).
- Styling via plain CSS in-repo; no external CDN required for core function (optional inline minimal styles).
- Tests in `tests/war_room/test_ui_render.py` assert `GET /` returns `200`, `text/html`, and HTML contains identifiable markers for board, chat, toast container, and task branch label pattern (substring tests acceptable).

## Files likely touched

- `cascade/war_room/templates/` or `cascade/war_room/views.py`
- `cascade/war_room/static/war_room.css`
- `cascade/war_room/static/war_room.js` (minimal fetch/poll only)
- `cascade/war_room/server.py`
- `tests/war_room/test_ui_render.py`

## Implementation notes

Prefer server-rendered first paint with small progressive enhancement JS for toasts/polling. Use relative API paths. Epic graph id for default chat: derive from board (single active epic or `epic_001` fallback documented). Do not embed Boss principal or cloud auth. Keep Task SWE transcript absent by design (DESIGN.md §10).

## Skills

_(none)_

## Test plan

`pytest tests/war_room/test_ui_render.py`

## Out of scope

- Amendment accept/reject (feat_006)
- Real comment sidecar read/write (feat_005)
- Boss agent (feat_008)
- GitHub or remote MR links
- TypeScript SPA or Node build pipeline

## Decision log

- `dec_013d` · 2026-10-09 · Feature Architect · **Server-rendered default home**
  Single-page War Room layout via Python templates + minimal static JS.
  Rationale: locked toolkit dec_013; localhost-only, no Node.
  Honors: DESIGN.md §10.1 surfaces; feat_003 default home constraint.
