---
id: task_067
title: War Room resolve_doc_worktree reads
tier: task
status: completed
parent: feat_014
children: []
depends_on:
  - task_065
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-14
updated: 2026-10-14
---

# War Room resolve_doc_worktree reads

## Parent Feature

[feat_014](../../features/3_completed/feat_014_workspace_contract.md) — Workspace contract and agent kickoff.

## Depends on

- task_065 — integration worktrees at activate/dispatch and repair

## Acceptance criteria

- **`resolve_doc_worktree(work_id, *, root) -> Path`** (e.g. `cascade/workspace/doc_root.py`):
  - Task spec → parent feature worktree (feature must be resolved even when querying task id).
  - Feature with worktree → feature worktree; feature without worktree (backlog / not dispatched) → parent epic worktree.
  - Active epic → epic worktree; backlog epic → trunk `root`.
  - Uses integration worktree registry / branch existence from task_065; does not create worktrees.
- **War Room read path** uses resolved root for:
  - **`GET /api/doc/{id}`** (`cascade/war_room/server.py` `_handle_doc`) — read markdown from worktree board tree.
  - **Plan viewer** (`/plan/{id}`): validate doc exists under resolved worktree; `plan_viewer.js` continues to fetch `/api/doc/` (no checkout in operator cwd).
  - **Attach** (`cascade/war_room/sidecar_routes.handle_post_attach`): resolve briefing/comments/chat doc reads from worktree; **`POST /api/attach` on backlog feature** (feature in `1_backlog`, no `feat/{id}` worktree) returns **4xx** with message matching feat_014 toast intent (“dispatch the feature to open its room”); does **not** call `dispatch_feature` or create worktree.
  - **Combined board view** (`board_view_from_index` / `list_board` if already merged) lenses epic/feature cards from correct worktrees per feat_014 home board rules (minimum: active feature cards and task rows read feature worktree specs).
- **Comments and chat stores** (`cascade/comments/store.py`, `cascade/war_room/chat_store.py`): append/read paths under the owning team's worktree (`docs/_comments`, `docs/_war_room/chat`), not trunk copies when teams are dispatched.
- **Attach / View plan do not change `--root` branch** (regression: trunk stays product trunk in git tests).
- **Tests** (`tests/war_room/test_resolve_worktree.py`):
  - Backlog feature: View plan reads spec from epic worktree; Attach refused.
  - Dispatched feature: Attach + View plan read live spec from feature worktree.
  - Task View plan reads task md from feature worktree.
  - Active epic attach uses epic worktree.

## Files likely touched

- `cascade/workspace/doc_root.py` (`resolve_doc_worktree`)
- `cascade/war_room/server.py`
- `cascade/war_room/sidecar_routes.py`
- `cascade/war_room/serialize.py` / `views.py` (board lens)
- `cascade/board/store.py` (`read_doc` optional `root` vs worktree root parameter)
- `cascade/comments/store.py`
- `cascade/war_room/chat_store.py`
- `cascade/war_room/static/war_room.js` (toast on attach refusal if API returns error)
- `tests/war_room/test_resolve_worktree.py`

## Implementation notes

- **`read_doc(work_id, root=trunk)`** may need **`read_doc_in_worktree(work_id, worktree_root)`** to avoid breaking dogfood single-tree mode — keep trunk-only tests passing via resolve falling back to trunk.
- **Risk (supervisor merged board)**: feat_014 says supervisor view aggregates trunk + worktrees; if full aggregation is large, implement read paths for attach/plan first and document remaining board API gaps in tests.
- **Risk (stale spec on epic branch)**: after dispatch, feature room must not read epic-branch copy — covered by resolve to feature worktree.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/war_room/test_resolve_worktree.py tests/war_room/test_dispatch_routes.py -q`

## Out of scope

- Flight report UI (task_068)
- `kickoff_turn` (task_066) except ensuring attach still does not call model
- Merge retargeting (task_069)
